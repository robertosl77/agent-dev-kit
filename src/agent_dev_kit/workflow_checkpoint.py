"""Private, atomic, local workflow checkpoints.

Only data needed to restore safe approval boundaries is persisted. This is
not a model-session replay log; in-flight action runs are never retried.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import time
from typing import Any

from agent_dev_kit.orchestration import AgentGateDecision, OrchestrationTrace, RequestProfile
from agent_dev_kit.task_plan import TaskNode, TaskPlan


VERSION = 1


def encode_plan(plan: TaskPlan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "request": plan.request,
        "nodes": [asdict(item) for item in plan.nodes],
        "required_disabled_agents": list(plan.required_disabled_agents),
        "notes": plan.notes,
        "profile": asdict(plan.profile) if plan.profile else None,
        "agent_decisions": [asdict(item) for item in plan.agent_decisions],
        "decisions_explicit": plan.decisions_explicit,
        "independent_risk_flags": list(plan.independent_risk_flags),
        "policy_activations": list(plan.policy_activations),
        "policy_required_agents": list(plan.policy_required_agents),
        "provider_calls": plan.provider_calls,
        "revisits": plan.revisits,
        "node_attempts": dict(plan.node_attempts),
        "calls_avoided_by_reuse": plan.calls_avoided_by_reuse,
        "execution_status": plan.execution_status,
        "story_approved": plan.story_approved,
        "trace": plan.trace.to_dict() if plan.trace else None,
    }


def decode_plan(payload: dict[str, Any] | None) -> TaskPlan | None:
    if payload is None:
        return None
    profile = payload.get("profile")
    plan = TaskPlan(
        request=str(payload["request"]),
        nodes=[TaskNode(
            id=str(item["id"]),
            agent=str(item["agent"]),
            objective=str(item["objective"]),
            phase=str(item["phase"]),
            depends_on=tuple(item.get("depends_on") or ()),
            status=str(item.get("status", "pending")),
            output=item.get("output"),
            evidence=dict(item.get("evidence") or {}),
        ) for item in payload["nodes"]],
        required_disabled_agents=tuple(payload.get("required_disabled_agents") or ()),
        notes=payload.get("notes"),
        profile=RequestProfile(
            summary=profile["summary"],
            classification=profile["classification"],
            risk_flags=tuple(profile.get("risk_flags") or ()),
            durable_artifacts=tuple(profile.get("durable_artifacts") or ()),
        ) if profile else None,
        agent_decisions=tuple(
            AgentGateDecision(**item) for item in payload.get("agent_decisions") or ()
        ),
        decisions_explicit=bool(payload.get("decisions_explicit")),
        independent_risk_flags=tuple(payload.get("independent_risk_flags") or ()),
        policy_activations=tuple(payload.get("policy_activations") or ()),
        policy_required_agents=tuple(payload.get("policy_required_agents") or ()),
        provider_calls=int(payload.get("provider_calls") or 0),
        revisits=int(payload.get("revisits") or 0),
        node_attempts=dict(payload.get("node_attempts") or {}),
        calls_avoided_by_reuse=int(payload.get("calls_avoided_by_reuse") or 0),
        execution_status=str(payload.get("execution_status") or "planned"),
        story_approved=bool(payload.get("story_approved")),
    )
    trace = payload.get("trace")
    if trace:
        # trace.to_dict stores JSON-compatible collections. Normalize fields
        # that are tuples/dataclasses in the runtime structure.
        data = {key: trace[key] for key in
                (field.name for field in fields(OrchestrationTrace))
                if key in trace and key not in {"persisted", "last_persisted_status"}}
        for key in ("risk_flags", "durable_artifacts", "independent_risk_flags", "policy_activations", "dag"):
            if key in data:
                data[key] = tuple(data[key])
        data["agent_decisions"] = tuple(
            AgentGateDecision(**item) for item in data.get("agent_decisions", ())
        )
        plan.trace = OrchestrationTrace(**data)
    plan.validate_structure()
    return plan


class WorkflowCheckpointStore:
    def __init__(self, root: Path):
        # Never create an untracked file inside the consumer's Git checkout.
        # Even .agent-dev-kit/runtime may be unignored in arbitrary projects.
        location = os.environ.get("AGENT_DEV_KIT_STATE_HOME")
        if not location:
            if os.name == "nt":
                location = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            else:
                location = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
        project_key = sha256(
            os.fsencode(str(Path(root).resolve()))
        ).hexdigest()[:32]
        self.directory = Path(location).expanduser().resolve() / "agent-dev-kit" / "mcp-workflows" / project_key

    def _path(self, ident: str) -> Path:
        if not ident.startswith("workflow_") or len(ident) != 41:
            raise ValueError("Invalid workflow id.")
        if not all(ch in "0123456789abcdef" for ch in ident[9:]):
            raise ValueError("Invalid workflow id.")
        return self.directory / (ident + ".json")

    def save(self, ident: str, data: dict[str, Any]) -> None:
        path = self._path(ident)
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {"version": VERSION, "workflow_id": ident, "saved_at": time(), **data}
        temp_name = None
        try:
            with NamedTemporaryFile("w", encoding="utf-8", dir=self.directory,
                                    prefix=".pending-", suffix=".json",
                                    delete=False) as f:
                temp_name = f.name
                os.chmod(temp_name, 0o600)
                json.dump(payload, f, ensure_ascii=False, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, path)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)

    def load(self, ident: str, ttl: float) -> dict[str, Any] | None:
        path = self._path(ident)
        if not path.is_file() or path.is_symlink():
            return None
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if (data.get("version") != VERSION or data.get("workflow_id") != ident):
            raise ValueError("Unsupported workflow checkpoint.")
        if time() - float(data.get("saved_at", 0)) >= ttl:
            path.unlink()
            return None
        return data

    def delete(self, ident: str) -> None:
        path = self._path(ident)
        if path.exists() and not path.is_symlink():
            path.unlink()
