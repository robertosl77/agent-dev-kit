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
