from dataclasses import dataclass
from typing import Any

from agent_dev_kit.agent_catalog import create_enabled_agents
from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider, ProviderRunResult
from agent_dev_kit.tooling import ToolRegistry


@dataclass(slots=True)
class DevAgentKit:
    """Runtime-ready set of enabled agents for one consuming project."""

    config: ProjectAgentDevKitConfig
    provider: AgentProvider
    agents: dict[str, AgentHandle]

    @classmethod
    def build(
        cls,
        config: ProjectAgentDevKitConfig,
        provider: AgentProvider,
        *,
        tool_registry: ToolRegistry | None = None,
    ) -> "DevAgentKit":
        return cls(
            config=config,
            provider=provider,
            agents=create_enabled_agents(
                provider,
                config,
                tool_registry=tool_registry,
            ),
        )

    def conversation(
        self,
        *,
        session: Any | None = None,
        start_agent: str | None = None,
    ) -> "DevConversation":
        return DevConversation(
            kit=self,
            session=session,
            active_agent=self._resolve_start_agent(start_agent),
        )

    def _resolve_start_agent(self, start_agent: str | None) -> AgentHandle:
        if start_agent is not None:
            try:
                return self.agents[start_agent]
            except KeyError as exc:
                raise ValueError(
                    f"Agent '{start_agent}' is not enabled in this project."
                ) from exc

        if "triage" in self.agents:
            return self.agents["triage"]

        if len(self.agents) == 1:
            return next(iter(self.agents.values()))

        raise ValueError(
            "No Triage agent is enabled and more than one specialist is active. "
            "Specify start_agent explicitly."
        )


@dataclass(slots=True)
class DevConversation:
    """Conversation that persists the last active specialist between turns."""

    kit: DevAgentKit
    session: Any | None
    active_agent: AgentHandle

    async def ask(self, message: str) -> ProviderRunResult:
        result = await self.kit.provider.run(
            self.active_agent,
            message,
            session=self.session,
        )
        self.active_agent = self._canonical_handle(result.active_agent)
        return result

    def ask_sync(self, message: str) -> ProviderRunResult:
        result = self.kit.provider.run_sync(
            self.active_agent,
            message,
            session=self.session,
        )
        self.active_agent = self._canonical_handle(result.active_agent)
        return result

    def reset_route(self) -> None:
        if "triage" not in self.kit.agents:
            raise ValueError("Triage is not enabled for this project.")
        self.active_agent = self.kit.agents["triage"]

    def route_to(self, key: str) -> None:
        try:
            self.active_agent = self.kit.agents[key]
        except KeyError as exc:
            raise ValueError(
                f"Agent '{key}' is not enabled in this project."
            ) from exc

    def _canonical_handle(self, result_handle: AgentHandle) -> AgentHandle:
        for handle in self.kit.agents.values():
            if handle.native is result_handle.native:
                return handle

        for handle in self.kit.agents.values():
            if handle.name == result_handle.name:
                return handle

        raise ValueError(
            f"Provider returned unknown active agent '{result_handle.name}'."
        )
