from typing import Any, Sequence

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

    def __init__(self) -> None:
        try:
            from agents import Agent, Runner
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI provider requires the optional dependency. "
                "Install with: pip install -e '.[openai]'"
            ) from exc

        self._agent_class = Agent
        self._runner = Runner

    def create_agent(
        self,
        definition: AgentDefinition,
        *,
        handoffs: Sequence[AgentHandle] = (),
        tools: Sequence[ToolHandle] = (),
    ) -> AgentHandle:
        self._validate_handoffs(handoffs)
        self._validate_tools(tools)

        kwargs: dict[str, Any] = {
            "name": definition.name,
            "instructions": definition.instructions,
        }

        if definition.handoff_description:
            kwargs["handoff_description"] = definition.handoff_description
        if definition.model:
            kwargs["model"] = definition.model
        if handoffs:
            kwargs["handoffs"] = [item.native for item in handoffs]
        if tools:
            kwargs["tools"] = [item.native for item in tools]

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
            output=str(result.final_output),
            active_agent=AgentHandle(
                provider=self.key,
                name=active.name,
                native=active,
            ),
            native_result=result,
        )
