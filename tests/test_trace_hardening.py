from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_dev_kit.orchestration import (
    AgentGateDecision,
    OrchestrationTrace,
    OrchestrationTraceStore,
    RequestProfile,
    orchestration_config_from_mapping,
    resolve_project_trace_path,
)
from agent_dev_kit.project_config import ProjectAgentDevKitConfig
from agent_dev_kit.provider_config import ProviderConfig
from agent_dev_kit.providers.provider_base import (
    AgentHandle,
    AgentProvider,
    ProviderRunResult,
)
from agent_dev_kit.runtime import DevAgentKit
from agent_dev_kit.task_plan import TaskPlan, TaskPlanError


def trace(index: int, *, summary: str | None = None) -> OrchestrationTrace:
    return OrchestrationTrace(
        request_summary=summary or f"Request {index}",
        request_fingerprint=f"fingerprint-{index}",
        classification="backend_bug",
        risk_flags=("backend_change",),
        durable_artifacts=(),
        agent_decisions=(
            AgentGateDecision(
                agent="backend",
                selected=True,
                gate="backend_change",
                reason="Backend behavior changes.",
            ),
        ),
        dag=(
            {
                "id": "backend",
                "agent": "backend",
                "phase": "implementation",
                "depends_on": [],
            },
        ),
    )


def plan() -> TaskPlan:
    result = TaskPlan.from_payload(
        {
            "request": "Fix backend behavior",
            "profile": {
                "summary": "Fix backend behavior.",
                "classification": "backend_bug",
                "risk_flags": ["backend_change"],
                "durable_artifacts": [],
            },
            "agent_decisions": [
                {
                    "agent": "backend",
                    "selected": True,
                    "gate": "backend_change",
                    "reason": "Backend behavior changes.",
                }
            ],
            "required_disabled_agents": [],
            "notes": None,
            "nodes": [
                {
                    "id": "backend",
                    "agent": "backend",
                    "phase": "implementation",
                    "objective": "Fix behavior",
                    "depends_on": [],
                }
            ],
        },
        require_agent_decisions=True,
    )
    result.trace = trace(1)
    return result


class TraceProvider(AgentProvider):
    key = "fake"

    def __init__(self, *, fail_once=False, unexpected_handoff=False):
        self.fail_once = fail_once
        self.unexpected_handoff = unexpected_handoff
        self.failed = False

    def create_agent(self, definition, *, handoffs=(), tools=()):
        return AgentHandle(
            provider=self.key,
            name=definition.name,
            native={"name": definition.name},
        )

    def set_handoffs(self, agent, handoffs):
        self._validate_handle(agent)
        self._validate_handoffs(handoffs)

    async def run(self, agent, message, *, session=None):
        return self.run_sync(agent, message, session=session)

    def run_sync(self, agent, message, *, session=None):
        if self.fail_once and not self.failed:
            self.failed = True
            raise RuntimeError("temporary provider failure")
        if self.unexpected_handoff:
            return ProviderRunResult(
                output="handoff",
                active_agent=AgentHandle(
                    provider=self.key,
                    name="Agent Security",
                    native=object(),
                ),
            )
        return ProviderRunResult(output="done", active_agent=agent)


def config(tmp_path, *, trace_path=".agent-dev-kit/runtime/traces.jsonl"):
    return ProjectAgentDevKitConfig(
        name="Example",
        stack={},
        provider=ProviderConfig(provider="fake"),
        enabled_agents=("backend",),
        agents={},
        project_root=tmp_path,
        orchestration=orchestration_config_from_mapping(
            {
                "trace": {
                    "enabled": True,
                    "path": trace_path,
                    "max_entries": 100,
                }
            }
        ),
    )


def test_trace_path_rejects_parent_traversal(tmp_path):
    with pytest.raises(ValueError, match="inside the project root"):
        resolve_project_trace_path(tmp_path, "../outside.jsonl")


def test_trace_path_rejects_absolute_path_outside_project(tmp_path):
    outside = tmp_path.parent / "outside.jsonl"

    with pytest.raises(ValueError, match="inside the project root"):
        resolve_project_trace_path(tmp_path, outside)


def test_runtime_build_enforces_trace_path_sandbox(tmp_path):
    with pytest.raises(ValueError, match="inside the project root"):
        DevAgentKit.build(
            config(tmp_path, trace_path="../outside.jsonl"),
            TraceProvider(),
        )


def test_trace_store_retains_only_latest_entries_and_reads_incrementally(tmp_path):
    store = OrchestrationTraceStore(
        tmp_path / "traces.jsonl",
        max_entries=2,
    )

    for index in range(4):
        store.append(trace(index))

    rows = store.read()
    incremental = list(store.iter_read(limit=1))

    assert [row["request_fingerprint"] for row in rows] == [
        "fingerprint-2",
        "fingerprint-3",
    ]
    assert incremental[0]["request_fingerprint"] == "fingerprint-3"


def test_trace_store_serializes_concurrent_thread_writes(tmp_path):
    store = OrchestrationTraceStore(
        tmp_path / "traces.jsonl",
        max_entries=100,
    )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: store.append(trace(index)), range(30)))

    rows = store.read()

    assert len(rows) == 30
    assert len({row["request_fingerprint"] for row in rows}) == 30


def test_trace_summary_is_sanitized_and_bounded(tmp_path):
    store = OrchestrationTraceStore(tmp_path / "traces.jsonl")
    sensitive = (
        "Fix report\npassword=super-secret token:abc123 "
        + ("x" * 700)
    )

    store.append(trace(1, summary=sensitive))
    summary = store.read()[0]["request_summary"]

    assert "\n" not in summary
    assert "super-secret" not in summary
    assert "abc123" not in summary
    assert "[REDACTED]" in summary
    assert len(summary) <= 500


def test_interrupted_trace_is_persisted_then_completed_after_retry(tmp_path):
    provider = TraceProvider(fail_once=True)
    kit = DevAgentKit.build(config(tmp_path), provider)
    task = plan()

    with pytest.raises(RuntimeError, match="temporary provider failure"):
        kit.execute_plan_sync(task)

    assert kit.trace_store.read()[-1]["status"] == "interrupted"

    kit.execute_plan_sync(task)
    statuses = [row["status"] for row in kit.trace_store.read()]

    assert statuses == ["interrupted", "completed"]
    assert kit.trace_store.read()[-1]["agent_decisions"][0]["gate"] == (
        "backend_change"
    )


def test_unexpected_handoff_persists_blocked_trace(tmp_path):
    kit = DevAgentKit.build(
        config(tmp_path),
        TraceProvider(unexpected_handoff=True),
    )
    task = plan()

    with pytest.raises(TaskPlanError, match="handed off unexpectedly"):
        kit.execute_plan_sync(task)

    assert kit.trace_store.read()[-1]["status"] == "blocked"


def test_non_executable_plan_persists_failed_trace(tmp_path):
    kit = DevAgentKit.build(config(tmp_path), TraceProvider())
    task = plan()
    task.node("backend").status = "blocked"

    with pytest.raises(TaskPlanError, match="none are executable"):
        kit.execute_plan_sync(task)

    assert kit.trace_store.read()[-1]["status"] == "failed"
