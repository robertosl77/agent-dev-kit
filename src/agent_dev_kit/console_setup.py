"""Interactive provider/model/key selection for the console (M-073).

Decisions applied:

1. The key is asked on every run and never stored: it only lives in memory
   for this process. If the provider's environment variable exists, it is
   used without asking.
2. ``provider.name`` in project.yaml is the *preferred* provider: every
   supported provider is listed and the preferred one is selected with Enter.
3. The model is always asked, from the provider's live list. There is no
   preferred model. If the list cannot be fetched, the name can be typed.
3b. Model tags only show what the provider reports.
"""

from __future__ import annotations

import getpass
import sys
from dataclasses import dataclass, field, replace
from typing import Callable, TextIO

from agent_dev_kit.model_catalog import ModelOption, list_models
from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.provider_errors import ProviderError, normalize_provider_exception
from agent_dev_kit.provider_registry import BUILTIN_PROVIDERS, ProviderSpec


InputFn = Callable[[str], str]
ModelLister = Callable[[str, "str | None"], list[ModelOption]]
MAX_ATTEMPTS = 3


class SetupCancelled(RuntimeError):
    """Raised when the person cannot or does not complete the selection."""


@dataclass(slots=True)
class SessionCredentials:
    """In-memory keys for this process only. Never written anywhere."""

    _keys: dict[str, str] = field(default_factory=dict, repr=False)
    ask: Callable[[str], "str | None"] | None = field(default=None, repr=False)

    def set(self, provider: str, key: str) -> None:
        self._keys[provider] = key

    def __call__(self, provider: str) -> str | None:
        if provider in self._keys:
            return self._keys[provider]
        spec = BUILTIN_PROVIDERS.get(provider)
        if spec is not None and spec.key_from_env():
            return None  # the provider SDK reads its own environment variable
        if self.ask is not None:
            key = self.ask(provider)
            if key:
                self._keys[provider] = key
            return key
        return None

    def __repr__(self) -> str:  # never show keys, even when debugging
        return f"SessionCredentials(providers={sorted(self._keys)})"


@dataclass(frozen=True, slots=True)
class ConsoleSelection:
    provider: str
    model: str
    config: ProjectAgentDevKitConfig
    credentials: SessionCredentials


class ConsoleSetup:
    def __init__(
        self,
        *,
        input_fn: InputFn = input,
        secret_fn: InputFn = getpass.getpass,
        out: TextIO | None = None,
        model_lister: ModelLister | None = None,
        providers: dict[str, ProviderSpec] | None = None,
    ) -> None:
        self.input_fn = input_fn
        self.secret_fn = secret_fn
        self.out = out or sys.stdout
        self.model_lister = model_lister or (
            lambda provider, key: list_models(provider, key)
        )
        self.providers = providers or BUILTIN_PROVIDERS

    def run(
        self,
        config: ProjectAgentDevKitConfig,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> ConsoleSelection:
        credentials = SessionCredentials(ask=self._ask_fallback_key)

        chosen = self._normalize_provider(provider) if provider else self.choose_provider(
            config.provider.provider
        )
        spec = self.providers[chosen]
        if not spec.is_installed():
            raise SetupCancelled(self._not_installed(spec))

        key = self.resolve_key(spec)
        if key is not None:
            credentials.set(chosen, key)

        chosen_model = model.strip() if model else self.choose_model(chosen, key)

        provider_config = replace(
            config.provider,
            provider=chosen,
            default_model=chosen_model,
            options=(
                dict(config.provider.options)
                if chosen == config.provider.provider
                else {}
            ),
        )
        return ConsoleSelection(
            provider=chosen,
            model=chosen_model,
            config=replace(config, provider=provider_config),
            credentials=credentials,
        )

    # -------------------------------------------------------------- provider

    def choose_provider(self, preferred: str | None) -> str:
        keys = list(self.providers)
        preferred_key = (preferred or "").strip().lower()
        self._print("¿Qué proveedor querés usar?")
        for index, key in enumerate(keys, start=1):
            spec = self.providers[key]
            notes = []
            if key == preferred_key:
                notes.append("preferido")
            if not spec.is_installed():
                notes.append(f"falta instalar: agent-dev-kit[{spec.extra}]")
            suffix = f"   ({', '.join(notes)})" if notes else ""
            self._print(f"  {index}) {spec.label}{suffix}")

        prompt = "> " if preferred_key not in keys else "> [Enter = preferido] "
        for _ in range(MAX_ATTEMPTS):
            answer = self.input_fn(prompt).strip()
            if not answer and preferred_key in keys:
                return preferred_key
            if answer.isdigit() and 1 <= int(answer) <= len(keys):
                return keys[int(answer) - 1]
            if answer.lower() in keys:
                return answer.lower()
            self._print("Opción inválida.")
        raise SetupCancelled("No se eligió un proveedor.")

    def _normalize_provider(self, value: str) -> str:
        key = value.strip().lower()
        if key not in self.providers:
            raise SetupCancelled(
                f"Proveedor desconocido '{value}'. Disponibles: "
                + ", ".join(self.providers)
            )
        return key

    # ------------------------------------------------------------------- key

    def resolve_key(self, spec: ProviderSpec) -> str | None:
        env_name = spec.env_var_in_use()
        if env_name:
            self._print(f"Usando la key de la variable de entorno {env_name}.")
            return None
        self._print(f"La key se obtiene en: {spec.key_url}")
        for _ in range(MAX_ATTEMPTS):
            key = self.secret_fn(f"Pegá tu key de {spec.label} (no se muestra): ").strip()
            if key:
                return key
            self._print("La key no puede quedar vacía.")
        raise SetupCancelled(f"No se ingresó la key de {spec.label}.")

    def _ask_fallback_key(self, provider: str) -> str | None:
        spec = self.providers.get(provider)
        if spec is None:
            return None
        self._print(f"Para continuar con {spec.label} hace falta su key.")
        try:
            return self.resolve_key(spec)
        except SetupCancelled:
            return None

    # ----------------------------------------------------------------- model

    def choose_model(self, provider: str, key: str | None) -> str:
        options: list[ModelOption] = []
        try:
            options = self.model_lister(provider, key)
        except Exception as exc:  # show the reason and allow typing the name
            error = exc if isinstance(exc, ProviderError) else normalize_provider_exception(
                exc, provider=provider
            )
            self._print(f"No se pudo obtener la lista de modelos: {error}")

        if options:
            self._print("¿Qué modelo?")
            width = max(len(item.id) for item in options)
            for index, item in enumerate(options, start=1):
                tags = " ".join(f"[{tag}]" for tag in item.tags)
                self._print(f"  {index}) {item.id.ljust(width)}  {tags}".rstrip())
            prompt = "> número o nombre del modelo: "
        else:
            prompt = "> escribí el nombre del modelo: "

        ids = [item.id for item in options]
        for _ in range(MAX_ATTEMPTS):
            answer = self.input_fn(prompt).strip()
            if options and answer.isdigit() and 1 <= int(answer) <= len(options):
                return options[int(answer) - 1].id
            if answer and (not options or answer in ids or not answer.isdigit()):
                if options and answer not in ids:
                    self._print(
                        f"Aviso: '{answer}' no figura en la lista del proveedor."
                    )
                return answer
            self._print("Opción inválida.")
        raise SetupCancelled("No se eligió un modelo.")

    # ----------------------------------------------------------------- utils

    def _not_installed(self, spec: ProviderSpec) -> str:
        return (
            f"{spec.label} no está instalado. Ejecutá: "
            f"pip install \"agent-dev-kit[{spec.extra}]\""
        )

    def _print(self, text: str) -> None:
        print(text, file=self.out)
