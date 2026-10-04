import pytest

from agent_dev_kit.task_plan import (
    DisabledAgentRequiredError,
    TaskPlan,
    TaskPlanError,
)


def test_task_plan_parses_and_exposes_ready_nodes():
    plan = TaskPlan.from_json(
        """{
          "request": "Fix data and UI",
          "required_disabled_agents": [],
          "nodes": [
            {
              "id": "architecture",
              "agent": "architecture",
              "objective": "Define boundaries",
              "depends_on": []
            },
            {
              "id": "backend",
              "agent": "backend",
              "objective": "Fix service",
              "depends_on": ["architecture"]
            },
            {
              "id": "ux",
              "agent": "ux_ui",
              "objective": "Define UX",
              "depends_on": ["architecture"]
            }
          ]
        }"""
    )

    assert [node.id for node in plan.ready_nodes()] == ["architecture"]

    plan.node("architecture").status = "completed"

    assert [node.id for node in plan.ready_nodes()] == ["backend", "ux"]


def test_task_plan_rejects_cycles():
    with pytest.raises(TaskPlanError, match="cycle"):
        TaskPlan.from_json(
            """{
              "request": "cycle",
              "nodes": [
                {
                  "id": "a",
                  "agent": "backend",
                  "objective": "a",
                  "depends_on": ["b"]
                },
                {
                  "id": "b",
                  "agent": "testing",
                  "objective": "b",
                  "depends_on": ["a"]
                }
              ]
            }"""
        )


def test_disabled_required_agent_blocks_execution():
    plan = TaskPlan.from_json(
        """{
          "request": "Improve UX",
          "required_disabled_agents": ["ux_ui"],
          "nodes": []
        }"""
    )

    with pytest.raises(DisabledAgentRequiredError) as exc:
        plan.validate_enabled(("triage", "frontend"))

    assert exc.value.agents == ("ux_ui",)


def test_orchestration_policy_requires_decision_for_each_enabled_specialist():
    plan = TaskPlan.from_json(
        """{
          "request": "Fix backend bug",
          "profile": {
            "summary": "Fix backend behavior.",
            "classification": "backend_bug",
            "risk_flags": ["backend_change", "behavior_regression"],
            "durable_artifacts": []
          },
          "agent_decisions": [
            {"agent": "backend", "selected": true, "gate": "backend_change", "reason": "Backend behavior changes."},
            {"agent": "testing", "selected": true, "gate": "behavior_regression", "reason": "Regression risk exists."}
          ],
          "required_disabled_agents": [],
          "nodes": [
            {"id": "backend", "agent": "backend", "phase": "implementation", "objective": "Fix behavior", "depends_on": []},
            {"id": "testing", "agent": "testing", "phase": "validation", "objective": "Regression test", "depends_on": ["backend"]}
          ]
        }"""
    )

    plan.validate_orchestration_policy(("triage", "backend", "testing"))


def test_security_risk_cannot_omit_security_agent():
    plan = TaskPlan.from_json(
        """{
          "request": "Add login endpoint",
          "profile": {
            "summary": "Add login endpoint.",
            "classification": "authentication_change",
            "risk_flags": ["security_surface", "backend_change"],
            "durable_artifacts": []
          },
          "agent_decisions": [
            {"agent": "backend", "selected": true, "gate": "backend_change", "reason": "Backend endpoint changes."},
            {"agent": "security", "selected": false, "gate": "security_surface", "reason": "Incorrectly omitted."}
          ],
          "required_disabled_agents": [],
          "nodes": [
            {"id": "backend", "agent": "backend", "objective": "Implement endpoint", "depends_on": []}
          ]
        }"""
    )

    with pytest.raises(TaskPlanError, match="security_surface"):
        plan.validate_orchestration_policy(("triage", "backend", "security"))


def test_durable_artifact_requires_documentation_when_enabled():
    plan = TaskPlan.from_json(
        """{
          "request": "Define API architecture",
          "profile": {
            "summary": "Define API architecture.",
            "classification": "architecture",
            "risk_flags": ["cross_layer"],
            "durable_artifacts": ["technical_spec"]
          },
          "agent_decisions": [
            {"agent": "architecture", "selected": true, "gate": "cross_layer", "reason": "Architecture is affected."},
            {"agent": "documentation", "selected": false, "gate": "durable_artifact", "reason": "Incorrectly omitted."}
          ],
          "required_disabled_agents": [],
          "nodes": [
            {"id": "architecture", "agent": "architecture", "phase": "design", "objective": "Define architecture", "depends_on": []}
          ]
        }"""
    )

    with pytest.raises(TaskPlanError, match="Documentation"):
        plan.validate_orchestration_policy(
            ("triage", "architecture", "documentation")
        )
