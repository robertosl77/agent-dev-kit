from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence

from agent_dev_kit.agent_definition import AgentDefinition
from agent_dev_kit.tooling import ToolHandle


@dataclass(slots=True)
class AgentHandle:
    """Opaque provider-specific agent wrapped by a provider-neutral handle."""

    provider: str
    name: str
    native: Any


@dataclass(slots=True)
class ProviderRunResult:
    """Normalized result returned by every provider implementation."""

    output: Any
    active_agent: AgentHandle
    native_result: Any | None = None
    usage: list[Any] = field(default_factory=list)  # list[UsageRecord] (M-036)


class AgentProvider(ABC):
    """Contract every concrete agent/model provider must implement."""

    key: str

    @abstractmethod
    def create_agent(
        self,
        definition: AgentDefinition,
        *,
        handoffs: Sequence[AgentHandle] = (),
        tools: Sequence[ToolHandle] = (),
    ) -> AgentHandle:
        raise NotImplementedError

    def supports_structured_output(self) -> bool:
        """Whether this provider can enforce a typed structured final output."""

        return False

    def create_structured_agent(
        self,
        definition: AgentDefinition,
        *,
        output_type: type[Any],
    ) -> AgentHandle:
        """Create an isolated agent whose final output is validated by the provider.

        Providers without native structured-output support intentionally fail
        here so callers can choose an explicit text fallback path.
        """

        raise NotImplementedError(
            f"Provider '{self.key}' does not support structured output."
        )

    def native_tool(self, tool: Any) -> Any:
        """Convert a built-in workspace tool (M-076) to this provider's format."""

        raise NotImplementedError(
            f"Provider '{self.key}' does not support built-in tools."
        )

    def set_handoffs(
        self,
        agent: AgentHandle,
        handoffs: Sequence[AgentHandle],
    ) -> None:
        """Configure handoffs after agent creation.

        Providers that support mutable routing graphs should override this.
        """

        self._validate_handle(agent)
        self._validate_handoffs(handoffs)
        raise NotImplementedError(
            f"Provider '{self.key}' does not support post-creation handoffs."
        )

    @abstractmethod
    async def run(
        self,
        agent: AgentHandle,
        message: str,
        *,
        session: Any | None = None,
    ) -> ProviderRunResult:
        raise NotImplementedError

    @abstractmethod
    def run_sync(
        self,
        agent: AgentHandle,
        message: str,
        *,
        session: Any | None = None,
    ) -> ProviderRunResult:
        raise NotImplementedError

    def _validate_handle(self, agent: AgentHandle) -> None:
        if agent.provider != self.key:
            raise ValueError(
                f"Agent belongs to provider '{agent.provider}', "
                f"not '{self.key}'."
            )

    def _validate_handoffs(self, handoffs: Sequence[AgentHandle]) -> None:
        for handoff in handoffs:
            self._validate_handle(handoff)

    def _validate_tools(self, tools: Sequence[ToolHandle]) -> None:
        for tool in tools:
            if tool.provider != self.key:
                raise ValueError(
                    f"Tool '{tool.key}' belongs to provider '{tool.provider}', "
                    f"not '{self.key}'."
                )
