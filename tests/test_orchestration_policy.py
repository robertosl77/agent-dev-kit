import json

import pytest

from agent_dev_kit.orchestration import orchestration_config_from_mapping
from agent_dev_kit.task_plan import TaskPlan, TaskPlanError


def _plan(
    *,
    request: str,
    decisions: str,
    nodes: str = "[]",
    risk_flags: str = "[]",
    durable_artifacts: str = "[]",
) -> TaskPlan:
    payload = {
        "request": request,
        "profile": {
            "summary": request,
            "classification": "test_change",
            "risk_flags": json.loads(risk_flags),
            "durable_artifacts": json.loads(durable_artifacts),
        },
        "agent_decisions": json.loads(decisions),
        "required_disabled_agents": [],
        "nodes": json.loads(nodes),
    }
    return TaskPlan.from_json(json.dumps(payload))


def test_unknown_risk_flag_is_rejected():
    with pytest.raises(TaskPlanError, match="Unknown risk flag"):
        _plan(
            request="Fix backend",
            risk_flags='["security_surafce"]',
            decisions="[]",
        )


def test_unknown_phase_is_rejected():
    with pytest.raises(TaskPlanError, match="Unknown task phase"):
        _plan(
            request="Fix backend",
            decisions="""[
              {
                "agent": "backend",
                "selected": true,
                "gate": "backend_change",
                "reason": "Backend changes."
              }
            ]""",
            nodes="""[
              {
                "id": "backend",
                "agent": "backend",
                "phase": "implementaton",
                "objective": "Fix behavior",
                "depends_on": []
              }
            ]""",
        )


def test_unknown_durable_artifact_is_rejected():
    with pytest.raises(TaskPlanError, match="Unknown durable artifact"):
        _plan(
            request="Document design",
            durable_artifacts='["tech_spec"]',
            decisions="[]",
        )


def test_independent_auth_classification_blocks_security_omission():
    plan = _plan(
        request="Change login authentication rules",
        decisions="""[
          {
            "agent": "security",
            "selected": false,
            "gate": "security_surface",
            "reason": "Triage incorrectly omitted security."
          }
        ]""",
    )

    with pytest.raises(TaskPlanError, match="security"):
        plan.validate_orchestration_policy(("triage", "security"))

    assert "auth_change" in plan.independent_risk_flags
    assert "security_surface" in plan.profile.risk_flags


def test_independent_schema_classification_blocks_database_omission():
    plan = _plan(
        request="Add a database column and migration",
        decisions="""[
          {
            "agent": "database",
            "selected": false,
            "gate": "persistence_change",
            "reason": "Triage incorrectly omitted database."
          }
        ]""",
    )

    with pytest.raises(TaskPlanError, match="database"):
        plan.validate_orchestration_policy(("triage", "database"))

    assert "schema_change" in plan.independent_risk_flags
    assert "persistence_change" in plan.profile.risk_flags


def test_project_policy_can_only_add_required_agents():
    config = orchestration_config_from_mapping(
        {
            "policies": [
                {
                    "id": "auth_requires_review",
                    "when": {"any_risk_flags": ["auth_change"]},
                    "require_agents": ["reviewer"],
                }
            ]
        }
    )
    plan = _plan(
        request="Change login authentication rules",
        decisions="""[
          {
            "agent": "security",
            "selected": true,
            "gate": "security_surface",
            "reason": "Authentication changes security behavior."
          },
          {
            "agent": "reviewer",
            "selected": false,
            "gate": "technical_review",
            "reason": "Triage incorrectly omitted review."
          }
        ]""",
        nodes="""[
          {
            "id": "security",
            "agent": "security",
            "phase": "validation",
            "objective": "Review authentication controls",
            "depends_on": []
          }
        ]""",
    )

    with pytest.raises(TaskPlanError, match="auth_requires_review"):
        plan.validate_orchestration_policy(
            ("triage", "security", "reviewer"),
            project_policies=config.policies,
        )

    assert plan.policy_activations == ("auth_requires_review",)


def test_project_policy_schema_rejects_unknown_risk():
    with pytest.raises(ValueError, match="Unknown risk flag"):
        orchestration_config_from_mapping(
            {
                "policies": [
                    {
                        "id": "bad_policy",
                        "when": {"any_risk_flags": ["authn_change"]},
                        "require_agents": ["security"],
                    }
                ]
            }
        )


def test_project_policy_schema_rejects_unknown_agent():
    with pytest.raises(ValueError, match="Unknown or unsupported required agent"):
        orchestration_config_from_mapping(
            {
                "policies": [
                    {
                        "id": "bad_agent",
                        "when": {"any_risk_flags": ["auth_change"]},
                        "require_agents": ["security_team"],
                    }
                ]
            }
        )
