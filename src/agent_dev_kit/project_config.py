from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.provider_config import ProviderConfig


@dataclass(frozen=True, slots=True)
class ContextualAgentConfig:
    """Project-specific additions for one reusable agent role."""

    key: str
    extra_instructions: tuple[str, ...] = ()
    project_rules: Mapping[str, Any] = field(default_factory=dict)
    tools: tuple[str, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProjectAgentDevKitConfig:
    """Resolved Agent Dev Kit configuration owned by a consuming project."""

    name: str
    stack: Mapping[str, Any]
    provider: ProviderConfig
    enabled_agents: tuple[str, ...]
    agents: Mapping[str, ContextualAgentConfig]
    raw: Mapping[str, Any] = field(default_factory=dict)

    def agent(self, key: str) -> ContextualAgentConfig | None:
        return self.agents.get(_normalize_agent_key(key))


def load_project_config(project_root: str | Path) -> ProjectAgentDevKitConfig:
    """Load .agent-dev-kit/project.yaml and optional per-agent YAML files."""

    root = Path(project_root)
    config_dir = root / ".agent-dev-kit"
    project_path = config_dir / "project.yaml"

    if not project_path.is_file():
        raise FileNotFoundError(
            f"Agent Dev Kit project configuration not found: {project_path}"
        )

    project_data = _load_yaml_mapping(project_path)

    project_section = project_data.get("project") or {}
    if not isinstance(project_section, dict):
        raise ValueError("'project' must be a mapping.")

    name = str(project_section.get("name") or "").strip()
    if not name:
        raise ValueError("'project.name' is required.")

    stack = project_data.get("stack") or {}
    if not isinstance(stack, dict):
        raise ValueError("'stack' must be a mapping.")

    provider_section = project_data.get("provider") or {}
    if not isinstance(provider_section, dict):
        raise ValueError("'provider' must be a mapping.")

    provider_name = str(provider_section.get("name") or "openai").strip()
    default_model = provider_section.get("default_model")
    provider_options = {
        key: value
        for key, value in provider_section.items()
        if key not in {"name", "default_model"}
    }

    agents_section = project_data.get("agents") or {}
    if not isinstance(agents_section, dict):
        raise ValueError("'agents' must be a mapping.")

    enabled = agents_section.get("enabled") or []
    if not isinstance(enabled, list):
        raise ValueError("'agents.enabled' must be a list.")

    enabled_agents = tuple(_normalize_agent_key(str(item)) for item in enabled)

    contextual_agents: dict[str, ContextualAgentConfig] = {}
    agents_dir = config_dir / "agents"
    if agents_dir.is_dir():
        for path in sorted(agents_dir.glob("*.yaml")):
            contextual = _load_agent_config(path)
            contextual_agents[contextual.key] = contextual

    return ProjectAgentDevKitConfig(
        name=name,
        stack=stack,
        provider=ProviderConfig(
            provider=provider_name,
            default_model=(
                str(default_model).strip()
                if default_model is not None
                else None
            ),
            options=provider_options,
        ),
        enabled_agents=enabled_agents,
        agents=contextual_agents,
        raw=project_data,
    )


def apply_project_context(
    definition: AgentDefinition,
    config: ProjectAgentDevKitConfig,
    agent_key: str,
) -> AgentDefinition:
    """Resolve native instructions with safe project-local context.

    Only explicit non-secret project metadata is injected: project name,
    configured stack, per-agent extra instructions, and project rules.
    Provider options are intentionally excluded because they may contain
    credentials or other sensitive values.
    """

    contextual = config.agent(agent_key)
    resolved = apply_contextual_config(definition, contextual)

    stack_yaml = yaml.safe_dump(
        dict(config.stack),
        allow_unicode=True,
        sort_keys=True,
        default_flow_style=False,
    ).strip()

    rules = contextual.project_rules if contextual is not None else {}
    rules_yaml = yaml.safe_dump(
        dict(rules),
        allow_unicode=True,
        sort_keys=True,
        default_flow_style=False,
    ).strip()

    context_parts = [
        "Consuming project context:",
        f"Project name: {config.name}",
        "Configured stack:",
        stack_yaml or "{}",
    ]

    if rules:
        context_parts.extend(
            [
                "Project rules for this agent:",
                rules_yaml,
            ]
        )

    instructions = (
        f"{resolved.instructions.rstrip()}\n\n"
        + "\n".join(context_parts)
        + "\n"
    )

    return AgentDefinition(
        name=resolved.name,
        instructions=instructions,
        handoff_description=resolved.handoff_description,
        model=resolved.model,
    )


def apply_contextual_config(
    definition: AgentDefinition,
    contextual: ContextualAgentConfig | None,
) -> AgentDefinition:
    """Combine reusable native instructions with project-local instructions."""

    if contextual is None or not contextual.extra_instructions:
        return definition

    additions = "\n".join(
        f"- {instruction}" for instruction in contextual.extra_instructions
    )
    instructions = (
        f"{definition.instructions.rstrip()}\n\n"
        "Project-specific contextual instructions:\n"
        f"{additions}\n"
    )

    return AgentDefinition(
        name=definition.name,
        instructions=instructions,
        handoff_description=definition.handoff_description,
        model=definition.model,
    )


def _load_agent_config(path: Path) -> ContextualAgentConfig:
    data = _load_yaml_mapping(path)
    key = _normalize_agent_key(str(data.get("agent") or path.stem))

    extra = data.get("extra_instructions") or []
    if not isinstance(extra, list):
        raise ValueError(
            f"'extra_instructions' must be a list in {path}."
        )

    rules = data.get("project_rules") or {}
    if not isinstance(rules, dict):
        raise ValueError(f"'project_rules' must be a mapping in {path}.")

    tools = data.get("tools") or []
    if not isinstance(tools, list):
        raise ValueError(f"'tools' must be a list in {path}.")

    return ContextualAgentConfig(
        key=key,
        extra_instructions=tuple(str(item).strip() for item in extra if str(item).strip()),
        project_rules=rules,
        tools=tuple(str(item).strip() for item in tools if str(item).strip()),
        raw=data,
    )


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}

    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")

    return data


def _normalize_agent_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")
