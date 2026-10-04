import json

from agent_dev_kit.orchestration_policy import AgentDecision
from agent_dev_kit.orchestration_trace import (
    JsonlTraceStore,
    OrchestrationTrace,
    fingerprint_request,
    suggest_trace_review_issues,
)


def make_trace(*, request_class="bug", retain=False):
    return OrchestrationTrace.create(
        request="Fix the same backend bug",
        request_summary="Fix backend bug",
        request_class=request_class,
        gates=("backend_change", "testing_required"),
        decisions=(
            AgentDecision("backend", True, "Changes server behavior."),
            AgentDecision("testing", True, "Regression risk."),
            AgentDecision(
                "architecture",
                False,
                "No structural impact.",
            ),
        ),
        dag=(
            {
                "id": "backend",
                "agent": "backend",
                "depends_on": [],
            },
            {
                "id": "testing",
                "agent": "testing",
                "depends_on": ["backend"],
            },
        ),
        issue_reference="T-123",
        retain_request_text=retain,
    )


def test_request_fingerprint_is_stable_after_whitespace_normalization():
    assert fingerprint_request("Fix   bug\nnow") == fingerprint_request(
        "Fix bug now"
    )


def test_trace_does_not_retain_raw_request_by_default():
    trace = make_trace()

    payload = trace.to_dict()

    assert "raw_request" not in payload
    assert payload["request_summary"] == "Fix backend bug"
    assert payload["request_fingerprint"]
    assert payload["selected_agents"] == ["backend", "testing"]
    assert payload["considered_omitted"] == [
        {
            "agent": "architecture",
            "reason": "No structural impact.",
        }
    ]


def test_trace_can_retain_raw_request_only_when_explicitly_enabled():
    trace = make_trace(retain=True)

    assert trace.to_dict()["raw_request"] == "Fix the same backend bug"


def test_trace_records_calls_and_metrics():
    trace = make_trace()

    trace.record_call(
        stage="planning",
        agent="triage",
        provider="fake",
        duration_ms=12,
        context_chars=800,
    )
    trace.record_call(
        stage="execution",
        agent="backend",
        provider="fake",
        duration_ms=30,
        context_chars=400,
    )
    trace.record_call(
        stage="execution",
        agent="testing",
        provider="fake",
        duration_ms=20,
        context_chars=250,
    )
    trace.finish()

    assert trace.provider_calls == 3
    assert trace.revisits == 0
    assert trace.total_context_chars == 1450
    assert trace.status == "completed"
    assert trace.finished_at is not None


def test_jsonl_trace_store_persists_structured_trace(tmp_path):
    trace = make_trace()
    trace.finish()

    path = tmp_path / "runtime" / "orchestration.jsonl"
    JsonlTraceStore(path).save(trace)

    rows = path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    payload = json.loads(rows[0])
    assert payload["trace_id"] == trace.trace_id
    assert "raw_request" not in payload


def test_repeated_objective_signal_creates_issue_proposal_not_policy_change():
    traces = [make_trace(request_class="bug") for _ in range(3)]
    for trace in traces:
        trace.record_call(
            stage="execution",
            agent="backend",
            provider="fake",
            duration_ms=1,
            context_chars=10,
        )
        trace.record_call(
            stage="execution",
            agent="backend",
            provider="fake",
            duration_ms=1,
            context_chars=10,
        )

    proposals = suggest_trace_review_issues(
        traces,
        min_occurrences=3,
    )

    assert len(proposals) == 1
    assert "revisits" in proposals[0].title.lower()
    assert len(proposals[0].evidence) == 3
    assert "No automatic policy change" in proposals[0].body
