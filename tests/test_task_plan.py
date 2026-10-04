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


def test_policy_v1_plan_parses_gates_decisions_phases_and_artifacts():
    plan = TaskPlan.from_json(
        """{
          "policy_version": 1,
          "request": "Add feature and update technical spec",
          "request_summary": "Add backend feature and update technical spec.",
          "request_class": "feature",
          "issue_reference": "T-999",
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
              "reason": "Changes server behavior."
            },
            {
              "agent": "testing",
              "selected": true,
              "reason": "Behavior needs regression coverage."
            },
            {
              "agent": "documentation",
              "selected": true,
              "reason": "Technical spec must be updated."
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
              "objective": "Implement behavior.",
              "phase": "implementation",
              "depends_on": []
            },
            {
              "id": "testing",
              "agent": "testing",
              "objective": "Validate behavior.",
              "phase": "verification",
              "depends_on": ["backend"]
            },
            {
              "id": "documentation",
              "agent": "documentation",
              "objective": "Update technical spec.",
              "phase": "documentation",
              "depends_on": ["testing"]
            }
          ]
        }"""
    )

    plan.validate_policy(
        ("backend", "testing", "documentation")
    )

    assert plan.request_summary.startswith("Add backend")
    assert plan.request_class == "feature"
    assert plan.node("backend").phase == "implementation"
    assert plan.artifacts[0].kind == "technical_spec"


def test_policy_v1_rejects_durable_artifact_without_documentation():
    plan = TaskPlan.from_json(
        """{
          "policy_version": 1,
          "request": "Implement backend and write technical spec",
          "request_summary": "Implement backend and write technical spec.",
          "request_class": "feature",
          "gates": ["backend_change"],
          "forced_agents": [],
          "required_disabled_agents": [],
          "decisions": [
            {
              "agent": "backend",
              "selected": true,
              "reason": "Changes server behavior."
            }
          ],
          "artifacts": [
            {
              "kind": "technical_spec",
              "action": "create"
            }
          ],
          "nodes": [
            {
              "id": "backend",
              "agent": "backend",
              "objective": "Implement behavior.",
              "phase": "implementation",
              "depends_on": []
            }
          ]
        }"""
    )

    with pytest.raises(TaskPlanError, match="require Documentation"):
        plan.validate_policy(("backend", "documentation"))
