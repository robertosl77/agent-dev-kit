from agent_dev_kit.project_config import (
    DocumentationConfig,
    OrchestrationConfig,
    OrchestrationTraceConfig,
    ProjectAgentDevKitConfig,
)
from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.providers.provider_base import (
    AgentHandle,
    AgentProvider,
    ProviderRunResult,
)
from agent_dev_kit.runtime import DevAgentKit


class BrainProvider(AgentProvider):
    key = "fake"

    def __init__(self):
        self.messages = {}

    def create_agent(self, definition, *, handoffs=(), tools=()):
        return AgentHandle(
            provider=self.key,
            name=definition.name,
            native=definition,
        )

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        self.messages.setdefault(agent.name, []).append(message)

        if (
            agent.name == "Agent Triage"
            and "Planning-only operation" in message
        ):
            return ProviderRunResult(
                output="""{
                  "policy_version": 1,
                  "request": "Implement feature and update technical spec",
                  "request_summary": "Implement backend behavior and update the technical spec.",
                  "request_class": "feature",
                  "issue_reference": "T-321",
                  "gates": [
                    "backend_change",
                    "testing_required",
                    "durable_documentation"
                  ],
                  "forced_agents": [],
                  "required_disabled_agents": [],
                  "decisions": [
                    {
                      "agent": "backend",
                      "selected": true,
                      "reason": "Server behavior changes."
                    },
                    {
                      "agent": "testing",
                      "selected": true,
                      "reason": "Regression coverage is useful."
                    },
                    {
                      "agent": "documentation",
                      "selected": true,
                      "reason": "Technical spec was explicitly requested."
                    },
                    {
                      "agent": "architecture",
                      "selected": false,
                      "reason": "No structural decision is needed."
                    }
                  ],
                  "artifacts": [
                    {
                      "kind": "technical_spec",
                      "action": "update"
                    }
                  ],
                  "nodes": [
                    {
                      "id": "backend",
                      "agent": "backend",
                      "objective": "Implement the backend behavior.",
                      "phase": "implementation",
                      "depends_on": []
                    },
                    {
                      "id": "testing",
                      "agent": "testing",
                      "objective": "Add deterministic regression coverage.",
                      "phase": "verification",
                      "depends_on": ["backend"]
                    },
                    {
                      "id": "documentation",
                      "agent": "documentation",
                      "objective": "Update the technical specification.",
                      "phase": "documentation",
                      "depends_on": ["testing"]
                    }
                  ]
                }""",
                active_agent=agent,
            )

        return ProviderRunResult(
            output=f"done by {agent.name}",
            active_agent=agent,
        )


def test_runtime_uses_summary_templates_and_structured_trace(tmp_path):
    template = tmp_path / "docs" / "templates" / "technical.md"
    template.parent.mkdir(parents=True)
    template.write_text(
        "# Technical spec template\n## Design",
        encoding="utf-8",
    )

    config = ProjectAgentDevKitConfig(
        name="Example",
        stack={},
        provider=ProviderConfig(provider="fake"),
        enabled_agents=(
            "triage",
            "backend",
            "testing",
            "documentation",
        ),
        agents={},
        documentation=DocumentationConfig(
            templates={
                "technical_spec": "docs/templates/technical.md",
            }
        ),
        orchestration=OrchestrationConfig(
            trace=OrchestrationTraceConfig(
                path=".agent-dev-kit/runtime/orchestration.jsonl",
                retain_request_text=False,
            )
        ),
        project_root=tmp_path,
    )
    provider = BrainProvider()
    kit = DevAgentKit.build(config, provider)

    original = (
        "Implement the feature. SENTINEL_CONVERSATIONAL_NOISE_123 "
        "Also update the technical spec."
    )
    plan = kit.plan_task_sync(original)
    result = kit.execute_plan_sync(plan)

    assert result.is_complete
    assert plan.trace is not None
    assert plan.trace.provider_calls == 4
    assert plan.trace.revisits == 0
    assert plan.trace.raw_request is None

    backend_prompt = provider.messages["Agent Backend"][0]
    documentation_prompt = provider.messages["Agent Documentation"][0]

    assert "SENTINEL_CONVERSATIONAL_NOISE_123" not in backend_prompt
    assert "Implement backend behavior" in backend_prompt
    assert "# Technical spec template" not in backend_prompt
    assert "# Technical spec template" in documentation_prompt

    trace_path = (
        tmp_path
        / ".agent-dev-kit"
        / "runtime"
        / "orchestration.jsonl"
    )
    assert trace_path.is_file()
    persisted = trace_path.read_text(encoding="utf-8")
    assert "SENTINEL_CONVERSATIONAL_NOISE_123" not in persisted
    assert plan.trace.trace_id in persisted
