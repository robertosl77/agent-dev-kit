from agent_dev_kit.orchestration import (
    AgentGateDecision,
    OrchestrationTrace,
    OrchestrationTraceStore,
    detect_improvement_candidates,
    fingerprint_request,
)


def test_request_fingerprint_is_stable_for_whitespace_and_case():
    first = fingerprint_request("Fix   REPORT", "backend_bug")
    second = fingerprint_request("fix report", "backend_bug")

    assert first == second


def test_trace_store_persists_no_full_request_by_default(tmp_path):
    trace = OrchestrationTrace(
        request_summary="Fix report behavior.",
        request_fingerprint="abc123",
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
    store = OrchestrationTraceStore(tmp_path / "traces.jsonl")

    store.append(trace)
    rows = store.read()

    assert rows[0]["request_summary"] == "Fix report behavior."
    assert rows[0]["full_request"] is None
    assert trace.persisted is True


def test_repeated_inconsistent_routes_become_improvement_candidate():
    traces = [
        {
            "request_fingerprint": "same",
            "classification": "backend_bug",
            "agent_decisions": [
                {"agent": "backend", "selected": True},
                {"agent": "testing", "selected": selected_testing},
            ],
            "revisits": 0,
        }
        for selected_testing in (True, False, True)
    ]

    candidates = detect_improvement_candidates(
        traces,
        threshold=3,
    )

    assert any(
        item.kind == "inconsistent_routing"
        for item in candidates
    )
