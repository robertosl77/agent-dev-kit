from typing import Any, Mapping, Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.tooling import ToolHandle
from agent_dev_kit.provider_errors import normalize_provider_exception
from agent_dev_kit.providers.provider_base import (
    AgentHandle,
    AgentProvider,
    ProviderRunResult,
)


class OpenAIProvider(AgentProvider):
    """OpenAI Agents SDK adapter.

    The rest of Agent Dev Kit does not import the OpenAI SDK directly.
    """

    key = "openai"

    env_var = "OPENAI_API_KEY"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        try:
            from agents import Agent, Runner
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI provider requires the optional dependency. "
                "Install with: pip install 'agent-dev-kit[openai]'"
            ) from exc

        self._agent_class = Agent
        self._runner = Runner
        self.default_model = default_model
        self._run_config = None
        if api_key:
            # Key supplied at runtime (CLI menu): use it explicitly instead of
            # OPENAI_API_KEY. Tracing export would otherwise look for the
            # environment key and warn, so it is disabled in this mode.
            from agents import OpenAIProvider as AgentsOpenAIProvider
            from agents import RunConfig

            self._run_config = RunConfig(
                model_provider=AgentsOpenAIProvider(api_key=api_key),
                tracing_disabled=True,
            )

    def create_agent(
        self,
        definition: AgentDefinition,
        *,
        handoffs: Sequence[AgentHandle] = (),
        tools: Sequence[ToolHandle] = (),
    ) -> AgentHandle:
        return self._create_agent(
            definition,
            handoffs=handoffs,
            tools=tools,
        )

    def supports_structured_output(self) -> bool:
        return True

    def create_structured_agent(
        self,
        definition: AgentDefinition,
        *,
        output_type: type[Any],
    ) -> AgentHandle:
        return self._create_agent(
            definition,
            output_type=output_type,
        )

    def _create_agent(
        self,
        definition: AgentDefinition,
        *,
        handoffs: Sequence[AgentHandle] = (),
        tools: Sequence[ToolHandle] = (),
        output_type: type[Any] | None = None,
    ) -> AgentHandle:
        self._validate_handoffs(handoffs)
        self._validate_tools(tools)

        kwargs: dict[str, Any] = {
            "name": definition.name,
            "instructions": definition.instructions,
        }

        model = definition.model or self.default_model
        if definition.handoff_description:
            kwargs["handoff_description"] = definition.handoff_description
        if model:
            kwargs["model"] = model
        if handoffs:
            kwargs["handoffs"] = [item.native for item in handoffs]
        if tools:
            kwargs["tools"] = [item.native for item in tools]
        if output_type is not None:
            kwargs["output_type"] = output_type

        native = self._agent_class(**kwargs)
        return AgentHandle(
            provider=self.key,
            name=definition.name,
            native=native,
        )

    def set_handoffs(
        self,
        agent: AgentHandle,
        handoffs: Sequence[AgentHandle],
    ) -> None:
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)
        agent.native.handoffs = [item.native for item in handoffs]

    async def run(
        self,
        agent: AgentHandle,
        message: str,
        *,
        session: Any | None = None,
    ) -> ProviderRunResult:
        self._validate_handle(agent)

        kwargs: dict[str, Any] = {}
        if session is not None:
            kwargs["session"] = session
        if self._run_config is not None:
            kwargs["run_config"] = self._run_config

        try:
            result = await self._runner.run(
                agent.native,
                message,
                **kwargs,
            )
        except Exception as exc:
            raise normalize_provider_exception(
                exc,
                provider=self.key,
            ) from exc

        return self._normalize_result(result)

    def run_sync(
        self,
        agent: AgentHandle,
        message: str,
        *,
        session: Any | None = None,
    ) -> ProviderRunResult:
        self._validate_handle(agent)

        kwargs: dict[str, Any] = {}
        if session is not None:
            kwargs["session"] = session
        if self._run_config is not None:
            kwargs["run_config"] = self._run_config

        try:
            result = self._runner.run_sync(
                agent.native,
                message,
                **kwargs,
            )
        except Exception as exc:
            raise normalize_provider_exception(
                exc,
                provider=self.key,
            ) from exc

        return self._normalize_result(result)

    def _normalize_result(self, result: Any) -> ProviderRunResult:
        active = result.last_agent
        return ProviderRunResult(
            output=result.final_output,
            active_agent=AgentHandle(
                provider=self.key,
                name=active.name,
                native=active,
            ),
            native_result=result,
        )
