import pytest

from agent_dev_kit.orchestration_policy import (
    AgentDecision,
    OrchestrationPolicyError,
    required_agents_for_gates,
    validate_plan_policy,
)


@pytest.mark.parametrize(
    ("case", "gates", "expected"),
    [
        ("trivial visual", ("frontend_change",), ("frontend",)),
        (
            "relevant ux",
            ("ux_change", "frontend_change"),
            ("ux_ui", "frontend"),
        ),
        (
            "external input query",
            (
                "database_change",
                "backend_change",
                "security_risk",
                "testing_required",
                "review_required",
            ),
            ("database", "backend", "security", "testing", "reviewer"),
        ),
        (
            "password recovery",
            (
                "product_definition",
                "security_risk",
                "backend_change",
                "frontend_change",
                "testing_required",
                "review_required",
            ),
            (
                "product",
                "security",
                "backend",
                "frontend",
                "testing",
                "reviewer",
            ),
        ),
        (
            "backend regression",
            ("backend_change", "testing_required"),
            ("backend", "testing"),
        ),
        (
            "docs only",
            ("durable_documentation",),
            ("documentation",),
        ),
        (
            "performance",
            ("performance_concern", "backend_change"),
            ("performance", "backend"),
        ),
        (
            "deployment",
            ("devops_change",),
            ("devops",),
        ),
        (
            "architecture",
            ("architecture_change", "backend_change"),
            ("architecture", "backend"),
        ),
        (
            "large feature",
            (
                "product_definition",
                "architecture_change",
                "backend_change",
                "frontend_change",
                "testing_required",
                "review_required",
                "durable_documentation",
            ),
            (
                "product",
                "architecture",
                "backend",
                "frontend",
                "testing",
                "reviewer",
                "documentation",
            ),
        ),
    ],
)
def test_representative_gate_sets_have_minimum_expected_specialists(
    case,
    gates,
    expected,
):
    assert required_agents_for_gates(gates) == expected


def test_policy_rejects_agent_without_gate():
    with pytest.raises(OrchestrationPolicyError, match="no active gate"):
        validate_plan_policy(
            gates=("frontend_change",),
            forced_agents=(),
            decisions=(
                AgentDecision("frontend", True, "Changes the UI."),
                AgentDecision(
                    "architecture",
                    True,
                    "Added by habit.",
                ),
            ),
            planned_agents=("frontend", "architecture"),
            required_disabled_agents=(),
            enabled_agents=("frontend", "architecture"),
        )


def test_policy_rejects_missing_risk_specialist():
    with pytest.raises(OrchestrationPolicyError, match="missing specialist"):
        validate_plan_policy(
            gates=("backend_change", "security_risk"),
            forced_agents=(),
            decisions=(
                AgentDecision("backend", True, "Changes API logic."),
            ),
            planned_agents=("backend",),
            required_disabled_agents=(),
            enabled_agents=("backend", "security"),
        )


def test_policy_requires_disabled_specialist_to_be_declared():
    with pytest.raises(
        OrchestrationPolicyError,
        match="required disabled not declared",
    ):
        validate_plan_policy(
            gates=("ux_change", "frontend_change"),
            forced_agents=(),
            decisions=(
                AgentDecision("frontend", True, "Implements UI."),
                AgentDecision("ux_ui", True, "Defines UX."),
            ),
            planned_agents=("frontend",),
            required_disabled_agents=(),
            enabled_agents=("frontend",),
        )


def test_explicit_user_force_is_allowed_but_not_triage():
    assert required_agents_for_gates(
        ("frontend_change",),
        forced_agents=("documentation",),
    ) == ("frontend", "documentation")

    with pytest.raises(OrchestrationPolicyError, match="Triage"):
        required_agents_for_gates((), forced_agents=("triage",))
