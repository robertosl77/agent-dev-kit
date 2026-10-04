from dataclasses import dataclass
from typing import Any

from agent_dev_kit.agent_catalog import AVAILABLE_AGENT_KEYS, create_enabled_agents
from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider, ProviderRunResult
from agent_dev_kit.tooling import ToolRegistry
from agent_dev_kit.preferences import PreferenceProfile
from agent_dev_kit.task_plan import (
    TaskNode,
    TaskPlan,
    TaskPlanError,
    build_planning_prompt,
)


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
        preference_profile: PreferenceProfile | None = None,
    ) -> "DevAgentKit":
        return cls(
            config=config,
            provider=provider,
            agents=create_enabled_agents(
                provider,
                config,
                tool_registry=tool_registry,
                preference_profile=preference_profile,
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

    def plan_task_sync(
        self,
        request: str,
        *,
        session: Any | None = None,
    ) -> TaskPlan:
        """Ask Triage for a structured multi-specialist DAG."""

        if "triage" not in self.agents:
            raise ValueError(
                "Triage must be enabled to create a multi-agent task plan."
            )

        prompt = build_planning_prompt(
            request,
            enabled_agents=self.agents.keys(),
            available_agents=AVAILABLE_AGENT_KEYS,
        )
        result = self.provider.run_sync(
            self.agents["triage"],
            prompt,
            session=session,
        )
        return TaskPlan.from_json(result.output)

    async def plan_task(
        self,
        request: str,
        *,
        session: Any | None = None,
    ) -> TaskPlan:
        """Async variant of plan_task_sync."""

        if "triage" not in self.agents:
            raise ValueError(
                "Triage must be enabled to create a multi-agent task plan."
            )

        prompt = build_planning_prompt(
            request,
            enabled_agents=self.agents.keys(),
            available_agents=AVAILABLE_AGENT_KEYS,
        )
        result = await self.provider.run(
            self.agents["triage"],
            prompt,
            session=session,
        )
        return TaskPlan.from_json(result.output)

    def execute_plan_sync(
        self,
        plan: TaskPlan,
        *,
        session: Any | None = None,
    ) -> TaskPlan:
        """Execute ready DAG nodes sequentially while respecting dependencies."""

        plan.validate_structure()
        plan.validate_enabled(self.agents.keys())

        while not plan.is_complete:
            ready = plan.ready_nodes()
            if not ready:
                raise TaskPlanError(
                    "Task plan has pending nodes but none are executable."
                )

            for node in ready:
                self._execute_node_sync(plan, node, session=session)

        return plan

    async def execute_plan(
        self,
        plan: TaskPlan,
        *,
        session: Any | None = None,
    ) -> TaskPlan:
        """Async provider execution with deterministic DAG sequencing."""

        plan.validate_structure()
        plan.validate_enabled(self.agents.keys())

        while not plan.is_complete:
            ready = plan.ready_nodes()
            if not ready:
                raise TaskPlanError(
                    "Task plan has pending nodes but none are executable."
                )

            for node in ready:
                await self._execute_node(plan, node, session=session)

        return plan

    def _execute_node_sync(
        self,
        plan: TaskPlan,
        node: TaskNode,
        *,
        session: Any | None,
    ) -> None:
        handle = self.agents[node.agent]
        node.status = "running"
        result = self.provider.run_sync(
            handle,
            self._node_prompt(plan, node),
            session=session,
        )

        if result.active_agent.name != handle.name:
            node.status = "blocked"
            raise TaskPlanError(
                f"Node '{node.id}' handed off unexpectedly from "
                f"'{handle.name}' to '{result.active_agent.name}'. "
                "The task DAG owns cross-specialist sequencing."
            )

        node.output = result.output
        node.evidence = {
            "provider": self.provider.key,
            "active_agent": result.active_agent.name,
        }
        node.status = "completed"

    async def _execute_node(
        self,
        plan: TaskPlan,
        node: TaskNode,
        *,
        session: Any | None,
    ) -> None:
        handle = self.agents[node.agent]
        node.status = "running"
        result = await self.provider.run(
            handle,
            self._node_prompt(plan, node),
            session=session,
        )

        if result.active_agent.name != handle.name:
            node.status = "blocked"
            raise TaskPlanError(
                f"Node '{node.id}' handed off unexpectedly from "
                f"'{handle.name}' to '{result.active_agent.name}'. "
                "The task DAG owns cross-specialist sequencing."
            )

        node.output = result.output
        node.evidence = {
            "provider": self.provider.key,
            "active_agent": result.active_agent.name,
        }
        node.status = "completed"

    @staticmethod
    def _node_prompt(plan: TaskPlan, node: TaskNode) -> str:
        dependency_context = []
        for dependency_id in node.depends_on:
            dependency = plan.node(dependency_id)
            dependency_context.append(
                f"[{dependency.id} / {dependency.agent}]\n"
                f"{dependency.output or '(no output)'}"
            )

        dependencies = (
            "\n\n".join(dependency_context)
            if dependency_context
            else "(none)"
        )

        return (
            "Execute only this DAG node. Do not hand off to another "
            "specialist; cross-specialist sequencing is owned by the task "
            "plan. If another responsibility is required, report it as a "
            "blocker.\n\n"
            f"Original request:\n{plan.request}\n\n"
            f"Node id: {node.id}\n"
            f"Your responsibility: {node.agent}\n"
            f"Objective:\n{node.objective}\n\n"
            f"Completed dependency outputs:\n{dependencies}\n\n"
            "Return the node result and concise evidence useful to the "
            "following nodes and final documentation."
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
