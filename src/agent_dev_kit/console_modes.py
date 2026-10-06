"""Console modes: /plan, /task and /do (M-076).

    /plan  → Triage plans; nothing else runs.
    /task  → plan + each agent proposes, inspecting the repo with read tools.
    /do    → plan → OK → local task branch from develop → agents change files
             and run tests → diff + consumption → OK → local commit.
             Nothing is pushed.

Approvals (decision 5C): the plan is approved before any agent works, test
commands run without asking, other allowed commands ask, and the commit is
approved after seeing the diff and the consumption. Confirmations are local:
they do not consume tokens.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Callable, TextIO

from agent_dev_kit.execution import ProviderRuntime
from agent_dev_kit.git_actions import (
    GitActionError,
    branch_kind,
    branch_slug,
    current_branch,
    diff_stat,
    is_git_repository,
    issue_reference,
    local_gateway,
    uncommitted_changes,
)
from agent_dev_kit.git_policy import GitPolicyViolation
from agent_dev_kit.task_plan import DisabledAgentRequiredError, TaskPlan
from agent_dev_kit.usage import format_usage_line

YES = {"s", "si", "sí", "y", "yes"}


@dataclass(slots=True)
class ConsoleIO:
    input_fn: Callable[[str], str] = input
    out: TextIO = field(default_factory=lambda: sys.stdout)

    def say(self, text: str = "") -> None:
        print(text, file=self.out)

    def confirm(self, question: str) -> bool:
        return self.input_fn(f"{question} [s/N] ").strip().lower() in YES

    def ask(self, question: str) -> str:
        return self.input_fn(question).strip()


Confirm = Callable[..., bool]


def usage_stages(trace: Any) -> list[tuple[str, list[dict[str, Any]]]]:
    stages: dict[str, list[dict[str, Any]]] = {}
    for item in getattr(trace, "usage", None) or []:
        stages.setdefault(str(item.get("stage")), []).append(item)
    return list(stages.items())


def plan_summary(plan: TaskPlan, runtime: ProviderRuntime) -> list[str]:
    target = runtime.current_target
    model = runtime.kit.config.provider.default_model or "modelo por defecto"
    selected = sorted({node.agent for node in plan.nodes})
    enabled = [key for key in runtime.kit.agents if key != "triage"]
    lines = [f"Plan ({target.provider} · {model}):"]
    for index, node in enumerate(plan.nodes, start=1):
        depends = f" (después de {', '.join(node.depends_on)})" if node.depends_on else ""
        lines.append(
            f"  {index}) {node.id} · {node.agent} · {node.phase}{depends}"
        )
        lines.append(f"     {node.objective}")
    lines.append(
        f"Agentes: {', '.join(selected) or 'ninguno'} "
        f"({len(selected)} de {len(enabled)} habilitados) · nodos: {len(plan.nodes)}"
    )
    return lines


def _plan(runtime: ProviderRuntime, request: str, confirm_switch: Confirm) -> TaskPlan:
    plan = runtime.run_with_fallback_sync(
        lambda kit: kit.plan_task_sync(request),
        confirm_switch=confirm_switch,
    )
    missing = plan.missing_agents(runtime.kit.agents.keys())
    if missing:
        raise DisabledAgentRequiredError(missing)
    return plan


def run_plan_only(
    runtime: ProviderRuntime,
    request: str,
    *,
    io: ConsoleIO,
    confirm_switch: Confirm,
) -> TaskPlan:
    plan = _plan(runtime, request, confirm_switch)
    for line in plan_summary(plan, runtime):
        io.say(line)
    if plan.trace is not None:
        plan.trace.mode = "plan"
    runtime.kit.record_plan_only(plan)
    io.say(format_usage_line(usage_stages(plan.trace), runtime.project_config.pricing))
    return plan


def run_propose(
    runtime: ProviderRuntime,
    request: str,
    *,
    io: ConsoleIO,
    confirm_switch: Confirm,
) -> TaskPlan:
    if runtime.workspace is not None:
        runtime.workspace.events.clear()
    plan = _plan(runtime, request, confirm_switch)
    if runtime.workspace is not None:
        runtime.workspace.bind_trace(plan.trace)
    result = runtime.run_with_fallback_sync(
        lambda kit: kit.execute_plan_sync(plan),
        confirm_switch=confirm_switch,
    )
    for node in result.nodes:
        io.say(f"[{node.status}] {node.id} ({node.agent})\n{node.output or ''}")
    io.say(format_usage_line(usage_stages(result.trace), runtime.project_config.pricing))
    return result


@dataclass(slots=True)
class ActOutcome:
    status: str
    branch: str | None = None
    committed: bool = False
    plan: TaskPlan | None = None


def run_act(
    runtime: ProviderRuntime,
    request: str,
    *,
    io: ConsoleIO,
    confirm_switch: Confirm,
) -> ActOutcome:
    act_runtime = runtime if runtime.mode == "act" else runtime.with_mode("act")
    workspace = act_runtime.workspace
    if workspace is None:
        raise RuntimeError("Action mode needs a workspace (project root).")
    root = workspace.root
    config = act_runtime.project_config

    if not is_git_repository(root):
        raise GitActionError("El proyecto no es un repositorio git.")
    pending = uncommitted_changes(root)
    if pending:
        io.say("Hay cambios sin commitear en el repo. Guardalos o descartalos antes de /do:")
        for line in pending[:15]:
            io.say(f"  {line}")
        return ActOutcome(status="dirty_worktree")

    issue = issue_reference(request)
    if not issue and config.git_workflow.require_issue_reference:
        issue = io.ask("¿Issue de la tarea? (ej. #96 o T-066): ").lstrip("#") or None
        if not issue:
            io.say("Sin issue no se puede crear la rama (lo exige la política del proyecto).")
            return ActOutcome(status="missing_issue")

    # Check the base branch before spending tokens on planning.
    workflow = config.git_workflow
    gateway = local_gateway(root, workflow)
    verifier = gateway._verifier
    base = workflow.task_branch_base
    if not verifier.branch_exists(base):
        io.say(f"No existe la rama '{base}' en el repo local. No se gastó nada.")
        return ActOutcome(status="base_missing")
    if workflow.require_updated_base_before_task and not verifier.is_up_to_date(base):
        io.say(f"No se puede empezar: {verifier.reason}. No se gastó nada.")
        return ActOutcome(status="base_outdated")

    # OK 1 — approve the plan before any agent works (the cheap point to stop).
    workspace.events.clear()
    plan = _plan(act_runtime, request, confirm_switch)
    for line in plan_summary(plan, act_runtime):
        io.say(line)
    io.say(format_usage_line(usage_stages(plan.trace), config.pricing))
    if not io.confirm("¿Ejecutar este plan?"):
        act_runtime.kit.record_plan_only(plan)
        io.say("Plan descartado. No se tocó nada.")
        return ActOutcome(status="plan_rejected", plan=plan)

    # Local task branch from the integration branch, validated by the policy.
    branch = gateway.guard.task_branch_name(
        kind=branch_kind(request),
        issue=(issue or "tarea").lower(),
        slug=branch_slug(request, issue),
    )
    started_on = current_branch(root)
    try:
        gateway.create_task_branch(
            branch,
            base_branch=workflow.task_branch_base,
            issue_reference=issue,
        )
    except GitPolicyViolation as exc:
        reason = getattr(verifier, "reason", "")
        io.say(f"No se creó la rama: {exc}" + (f" ({reason})" if reason else ""))
        act_runtime.kit.record_plan_only(plan)
        return ActOutcome(status="branch_rejected", plan=plan)
    io.say(f"Rama local creada: {branch} (desde {workflow.task_branch_base})")

    # Agents work on the branch with write tools.
    workspace.bind_trace(plan.trace)
    result = act_runtime.run_with_fallback_sync(
        lambda kit: kit.execute_plan_sync(plan),
        confirm_switch=confirm_switch,
    )
    for node in result.nodes:
        io.say(f"[{node.status}] {node.id} ({node.agent})\n{node.output or ''}")

    changes = uncommitted_changes(root)
    commands = [
        event for event in workspace.events if event.get("tool") == "run_command"
    ]
    io.say("")
    io.say(f"Rama: {branch}")
    if changes:
        io.say("Cambios:")
        io.say(diff_stat(root) or "\n".join(changes))
    else:
        io.say("Los agentes no cambiaron archivos.")
    for event in commands:
        if "exit_code" in event:
            state = "OK" if event.get("ok") else f"falló (exit {event.get('exit_code')})"
        else:
            state = {
                "not_allowed": "rechazado: no está en workspace.test_commands ni allowed_commands",
                "rejected": "no lo aprobaste",
                "timeout": "excedió el tiempo",
            }.get(str(event.get("reason")), "no se ejecutó")
        io.say(f"Comando: {event.get('command')} → {state}")
    io.say(format_usage_line(usage_stages(result.trace), config.pricing))

    if not changes:
        return ActOutcome(status="no_changes", branch=branch, plan=result)

    # OK 4 — commit only after seeing the diff and the consumption.
    if not io.confirm("¿Commitear estos cambios en la rama local?"):
        io.say(
            f"Quedan sin commitear en {branch} para que los revises "
            f"(volver: git checkout {started_on})."
        )
        return ActOutcome(status="not_committed", branch=branch, plan=result)

    title = " ".join(request.replace(issue or "\0", " ").split())[:60] if issue else " ".join(request.split())[:60]
    message = f"{issue}: {title}" if issue else title
    message += (
        f"\n\nGenerado con agent-dev-kit /do "
        f"({act_runtime.current_target.provider} · {config.provider.default_model or 'default'})."
    )
    gateway.direct_write(branch, payload={"message": message})
    io.say(f"Commit local hecho en {branch}. No se hizo push: subila cuando lo decidas.")
    return ActOutcome(status="committed", branch=branch, committed=True, plan=result)
