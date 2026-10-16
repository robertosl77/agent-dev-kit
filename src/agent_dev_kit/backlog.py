"""Scrum backlog of an orchestrated task (console /plan, /backlog, /do).

The backlog is built by Scrum Master once the plan exists:

    items   → RF (user stories) and RNF (concrete non-functional work),
              each with acceptance criteria and its sprint;
    sprints → small increments, each one testable by the person;
    definition_of_done → cross-cutting RNF every item must meet.

The framework validates the shape (ids, types, sprint references); the model
only proposes the content.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from agent_dev_kit.planner_contract import StructuredBacklog

ITEM_TYPES = ("RF", "RNF")
ITEM_STATUSES = ("pending", "in_progress", "done")
SCRUM_AGENTS = frozenset({"scrum_master", "pmo"})


class BacklogError(ValueError):
    """The backlog proposed by the model is not valid."""


def plan_uses_scrum(plan: Any) -> bool:
    """Scrum applies when Triage selected Scrum Master or PMO for the plan."""

    return any(node.agent in SCRUM_AGENTS for node in getattr(plan, "nodes", ()))


def build_backlog_prompt(plan: Any, *, language: str | None = None) -> str:
    nodes = "\n".join(
        f"- {node.id} [{node.agent}] {node.objective}" for node in plan.nodes
    )
    summary = getattr(getattr(plan, "profile", None), "summary", "") or ""
    reply_language = (
        f"Write every text field in the project language ({language})."
        if language
        else "Write every text field in the language of the original request."
    )
    return f"""Build the Scrum product backlog for this task. Do not execute anything.

Original request from the person (source of truth):
{plan.request}

Triage summary: {summary}
Plan nodes decided by Triage:
{nodes}

Rules:
- Functional requirements are user stories, type "RF": title "Como <rol>, quiero <capacidad>, para <beneficio>".
- Non-functional requirements:
  - cross-cutting ones (performance, security, accessibility that every item must meet) go to
    definition_of_done, NOT to items;
  - concrete non-functional work (e.g. "migrar a HTTPS") is an item of type "RNF".
- ids: "HU-01", "HU-02"... for RF and "RNF-01"... for RNF. Unique.
- Every item has observable acceptance criteria and a sprint number.
- Sprints are numbered 1..N, small, and each ends in something the person can test
  (testable_result). A small request is a single sprint.
- Do not invent requirements that are not in the request; if something is a hypothesis,
  say so in its criteria.
- {reply_language}
"""


def _mapping(output: Any) -> Mapping[str, Any]:
    if isinstance(output, StructuredBacklog):
        return output.to_mapping()
    if isinstance(output, Mapping):
        return output
    if isinstance(output, str):
        text = output.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
            text = text.rsplit("```", 1)[0]
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise BacklogError(f"backlog is not valid JSON: {exc}") from exc
        if not isinstance(data, Mapping):
            raise BacklogError("backlog must be a JSON object")
        return data
    raise BacklogError(f"unsupported backlog output: {type(output).__name__}")


def parse_backlog(output: Any) -> dict[str, Any]:
    """Validate the model output and return the backlog with item statuses."""

    data = _mapping(output)
    items = data.get("items")
    sprints = data.get("sprints")
    dod = data.get("definition_of_done") or []
    if not isinstance(items, list) or not items:
        raise BacklogError("backlog needs at least one item")
    if not isinstance(sprints, list) or not sprints:
        raise BacklogError("backlog needs at least one sprint")

    numbers: list[int] = []
    clean_sprints = []
    for sprint in sprints:
        number = sprint.get("number")
        if not isinstance(number, int) or number < 1 or number in numbers:
            raise BacklogError(f"invalid or repeated sprint number: {number!r}")
        numbers.append(number)
        clean_sprints.append(
            {
                "number": number,
                "goal": str(sprint.get("goal") or "").strip(),
                "testable_result": str(sprint.get("testable_result") or "").strip(),
            }
        )

    seen: set[str] = set()
    clean_items = []
    for item in items:
        item_id = str(item.get("id") or "").strip()
        if not item_id or item_id in seen:
            raise BacklogError(f"invalid or repeated item id: {item_id!r}")
        seen.add(item_id)
        kind = str(item.get("type") or "").upper()
        if kind not in ITEM_TYPES:
            raise BacklogError(f"item {item_id}: type must be RF or RNF, got {kind!r}")
        sprint = item.get("sprint")
        if sprint not in numbers:
            raise BacklogError(f"item {item_id}: sprint {sprint!r} does not exist")
        criteria = [str(c).strip() for c in item.get("criteria") or [] if str(c).strip()]
        if not criteria:
            raise BacklogError(f"item {item_id}: needs acceptance criteria")
        clean_items.append(
            {
                "id": item_id,
                "type": kind,
                "title": str(item.get("title") or "").strip(),
                "criteria": criteria,
                "sprint": sprint,
                "status": "pending",
            }
        )

    for number in numbers:
        if not any(item["sprint"] == number for item in clean_items):
            raise BacklogError(f"sprint {number} has no items")

    return {
        "items": clean_items,
        "sprints": sorted(clean_sprints, key=lambda s: s["number"]),
        "definition_of_done": [str(x).strip() for x in dod if str(x).strip()],
    }


def next_sprint(backlog: Mapping[str, Any]) -> int | None:
    for sprint in backlog.get("sprints") or []:
        number = sprint["number"]
        if any(
            item["sprint"] == number and item["status"] != "done"
            for item in backlog.get("items") or []
        ):
            return number
    return None


def sprint_items(backlog: Mapping[str, Any], number: int) -> list[dict[str, Any]]:
    return [item for item in backlog.get("items") or [] if item["sprint"] == number]


def move_out_of_sprint(backlog: dict[str, Any], number: int, item_ids: list[str]) -> list[str]:
    """Move items to the next sprint (or leave them unassigned). Returns moved ids."""

    later = [s["number"] for s in backlog.get("sprints") or [] if s["number"] > number]
    target = later[0] if later else None
    moved = []
    wanted = {i.upper() for i in item_ids}
    for item in backlog.get("items") or []:
        if item["sprint"] == number and item["id"].upper() in wanted:
            item["sprint"] = target
            moved.append(item["id"])
    return moved


def sprint_request(original: str, backlog: Mapping[str, Any], number: int) -> str:
    """Request handed to the planner to execute one sprint."""

    sprint = next(s for s in backlog["sprints"] if s["number"] == number)
    lines = [
        original.strip(),
        "",
        f"Sprint {number} — objetivo: {sprint['goal']}",
        "Implementar SOLO estas historias/ítems (ya aprobados por la persona; "
        "no volver a pedir validación de historias):",
    ]
    for item in sprint_items(backlog, number):
        if item["status"] == "done":
            continue
        lines.append(f"- {item['id']} ({item['type']}) {item['title']}")
        lines += [f"    · {criterion}" for criterion in item["criteria"]]
    dod = backlog.get("definition_of_done") or []
    if dod:
        lines.append("Definition of Done (aplica a todo el sprint):")
        lines += [f"- {entry}" for entry in dod]
    lines.append(f"Al terminar, la persona debe poder probar: {sprint['testable_result']}")
    return "\n".join(lines)
