"""Comandos de la consola interactiva (`agent-dev-kit run`).

Implementa el catálogo de `commands.py` sobre el runtime:

    /input    acumula contexto y responde «Leído»
    /plan     arma el plan sin ejecutar; con Scrum, además el backlog
              (RF/RNF, sprints, Definition of Done); pide aprobarlo
    /grafo    JSON del último plan (con el backlog)
    /backlog  tabla del backlog
    /do       con Scrum: un sprint por vez (muestra el sprint, tu OK, ejecuta)
              sin Scrum: el plan acordado completo
    /testing  corre los tests declarados del proyecto y reporta (no corrige)

El plan y el backlog se guardan en `.agent-dev-kit/runtime/backlog.json`, así
/backlog, /grafo y el /do por sprints siguen en otra sesión. Un plan sin Scrum
de una sesión anterior se puede ver, pero para ejecutarlo hay que volver a
correr /plan.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_dev_kit.backlog import (
    move_out_of_sprint,
    next_sprint,
    plan_uses_scrum,
    sprint_items,
    sprint_request,
)
from agent_dev_kit.commands import NO_BACKLOG, NO_PLAN, READ_ACK
from agent_dev_kit.console_modes import (
    Confirm,
    ConsoleIO,
    YES,
    _facts,
    _plan,
    plan_summary,
    run_act,
    usage_stages,
)
from agent_dev_kit.execution import ProviderRuntime
from agent_dev_kit.task_plan import TaskPlan
from agent_dev_kit.usage import format_usage_line
from agent_dev_kit.workspace_tools import _command_argv

BACKLOG_FILE = Path(".agent-dev-kit") / "runtime" / "backlog.json"
OUTPUT_TAIL_LINES = 15
DONE_OUTCOMES = {"committed"}
STARTED_OUTCOMES = {"not_committed", "no_changes"}


@dataclass(slots=True)
class CommandSession:
    """Estado de una sesión de consola: contexto acumulado y plan vigente."""

    root: Path
    context: list[str] = field(default_factory=list)
    plan: TaskPlan | None = None
    agreed: bool = False
    backlog: dict[str, Any] | None = None
    adjustments: list[str] = field(default_factory=list)
    loaded: bool = False

    # ------------------------------------------------------------ persistence
    @property
    def backlog_path(self) -> Path:
        return self.root / BACKLOG_FILE

    def load(self) -> None:
        """Recover agreed state and backlog of a previous session (once)."""

        if self.loaded or self.plan is not None:
            return
        self.loaded = True
        data = self.load_snapshot()
        if not data:
            return
        self.agreed = bool(data.get("agreed"))
        if data.get("scrum"):
            self.backlog = data["scrum"]
            self.adjustments = list(data.get("adjustments") or [])
            if not self.context and data.get("request"):
                self.context = [data["request"]]

    def snapshot(self) -> dict[str, Any] | None:
        plan = self.plan
        if plan is None:
            return self.load_snapshot()
        trace = plan.trace.to_dict() if plan.trace is not None else {}
        return {
            "request": plan.request,
            "agreed": self.agreed,
            "status": plan.execution_status,
            "scrum": self.backlog,
            "adjustments": self.adjustments,
            "nodes": [
                {
                    "id": node.id,
                    "agent": node.agent,
                    "objective": node.objective,
                    "depends_on": list(node.depends_on),
                    "status": node.status,
                }
                for node in plan.nodes
            ],
            "trace": trace,
        }

    def save(self) -> None:
        data = self.snapshot()
        if data is None:
            return
        if self.plan is None:
            # Only the backlog/agreement changed (e.g. a sprint of a previous session).
            data = {**data, "agreed": self.agreed, "scrum": self.backlog,
                    "adjustments": self.adjustments}
        self.backlog_path.parent.mkdir(parents=True, exist_ok=True)
        self.backlog_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def load_snapshot(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.backlog_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    @property
    def request(self) -> str:
        return "\n\n".join(part for part in self.context if part.strip())


# ------------------------------------------------------------------ helpers
def backlog_lines(backlog: dict[str, Any]) -> list[str]:
    lines = [f"  {'Ítem':<8} {'Tipo':<4} {'Sprint':<6} {'Estado':<11} Título"]
    for item in backlog["items"]:
        sprint = "—" if item["sprint"] is None else str(item["sprint"])
        lines.append(
            f"  {item['id']:<8} {item['type']:<4} {sprint:<6} {item['status']:<11} {item['title']}"
        )
    for sprint in backlog["sprints"]:
        lines.append(f"  Sprint {sprint['number']}: {sprint['goal']} → probar: {sprint['testable_result']}")
    dod = backlog.get("definition_of_done") or []
    if dod:
        lines.append("  Definition of Done (RNF transversales):")
        lines += [f"    - {entry}" for entry in dod]
    return lines


def _sprint_preview(backlog: dict[str, Any], number: int) -> list[str]:
    sprint = next(s for s in backlog["sprints"] if s["number"] == number)
    lines = [f"Sprint {number} — {sprint['goal']}"]
    for item in sprint_items(backlog, number):
        mark = " (hecho)" if item["status"] == "done" else ""
        lines.append(f"  {item['id']} ({item['type']}) {item['title']}{mark}")
        lines += [f"     · {criterion}" for criterion in item["criteria"]]
    lines.append(f"  Al terminar vas a poder probar: {sprint['testable_result']}")
    return lines


def _parse_sprint_argument(argument: str) -> int | None | str:
    text = argument.strip().lower()
    if not text:
        return None
    parts = text.split()
    if parts[0] == "sprint" and len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    return "invalid"


# ----------------------------------------------------------------- commands
def cmd_input(session: CommandSession, argument: str, *, io: ConsoleIO) -> None:
    if argument.strip():
        session.context.append(argument.strip())
    io.say(READ_ACK)


def cmd_plan(
    session: CommandSession,
    runtime: ProviderRuntime,
    argument: str,
    *,
    io: ConsoleIO,
    confirm_switch: Confirm,
) -> None:
    session.load()
    if argument.strip():
        session.context.append(argument.strip())
    request = session.request
    if not request:
        io.say("No hay nada para planificar: usá /input <texto> o /plan <texto>.")
        return

    # Re-plan: the previous agreement no longer holds (H2).
    session.agreed = False
    session.backlog = None
    session.adjustments = []
    act_runtime = runtime if runtime.mode == "act" else runtime.with_mode("act")
    plan = _plan(act_runtime, request, confirm_switch)
    session.plan = plan
    for line in plan_summary(plan, act_runtime):
        io.say(line)

    scrum = plan_uses_scrum(plan) and act_runtime.kit.backlog_agent is not None
    question = "¿Aprobás el plan?"
    if scrum:
        session.backlog = act_runtime.run_with_fallback_sync(
            lambda kit: kit.build_backlog_sync(plan),
            confirm_switch=confirm_switch,
        )
        io.say("Backlog propuesto (Scrum):")
        for line in backlog_lines(session.backlog):
            io.say(line)
        question = "¿Aprobás el plan y el backlog?"
    elif plan.requires_story_approval and runtime.workspace is not None:
        workspace = runtime.workspace
        preview = act_runtime.with_mode("propose")
        workspace.bind_trace(plan.trace)
        plan.facts = _facts(workspace, runtime.project_config, request)
        preview.run_with_fallback_sync(
            lambda kit: kit.execute_plan_sync(plan, intake_only=True),
            confirm_switch=confirm_switch,
        )
        for node in plan.nodes:
            if node.agent == "scrum_master":
                io.say(f"Historias de usuario y criterios propuestos:\n{node.output or ''}")
        question = "¿Aprobás el plan y las historias?"
    io.say(format_usage_line(usage_stages(plan.trace), runtime.project_config.pricing))

    if io.confirm(question):
        session.agreed = True
        if plan.requires_story_approval and not scrum:
            plan.story_approved = True
        io.say("Plan acordado. /backlog para verlo, /do para ejecutarlo.")
    else:
        io.say("Plan no acordado. Ajustalo con /input o /plan <detalle>.")
    if plan.trace is not None:
        plan.trace.mode = "plan"
    act_runtime.kit.record_plan_only(plan)
    session.save()


def cmd_grafo(session: CommandSession, *, io: ConsoleIO) -> None:
    data = session.snapshot()
    if data is None:
        io.say(NO_PLAN)
        return
    io.say(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def cmd_backlog(session: CommandSession, *, io: ConsoleIO) -> None:
    session.load()
    data = session.snapshot()
    if data is None:
        io.say(NO_BACKLOG)
        return
    estado = "acordado" if session.agreed or data.get("agreed") else "no acordado"
    backlog = session.backlog or data.get("scrum")
    if backlog:
        io.say(f"Backlog ({estado}):")
        for line in backlog_lines(backlog):
            io.say(line)
        return
    nodes = data.get("nodes") or []
    if not nodes:
        io.say(NO_BACKLOG)
        return
    io.say(f"Backlog ({estado}, sin Scrum: pasos del plan):")
    io.say(f"  {'Paso':<10} {'Agente':<14} {'Estado':<10} Objetivo")
    for node in nodes:
        io.say(f"  {node['id']:<10} {node['agent']:<14} {node['status']:<10} {node['objective']}")


def _do_sprint(
    session: CommandSession,
    runtime: ProviderRuntime,
    argument: str,
    *,
    io: ConsoleIO,
    confirm_switch: Confirm,
) -> None:
    backlog = session.backlog
    assert backlog is not None
    wanted = _parse_sprint_argument(argument)
    if wanted == "invalid":
        io.say("Usá /do o /do sprint N.")
        return
    number = wanted if isinstance(wanted, int) else next_sprint(backlog)
    if number is None:
        io.say("No quedan sprints pendientes: el backlog está completo.")
        return
    if not any(s["number"] == number for s in backlog["sprints"]):
        io.say(f"No existe el sprint {number}.")
        return

    while True:
        for line in _sprint_preview(backlog, number):
            io.say(line)
        answer = io.ask(
            "¿Ejecutar este sprint? [s = sí · n = no · -HU-04 = sacar ítems del sprint] "
        ).strip()
        if answer.lower() in YES:
            break
        if answer.startswith("-"):
            ids = [part.lstrip("-") for part in answer.replace(",", " ").split()]
            moved = move_out_of_sprint(backlog, number, ids)
            if moved:
                note = f"Sprint {number}: se sacaron {', '.join(moved)}"
                session.adjustments.append(note)
                io.say(f"{note}.")
                session.save()
            else:
                io.say("Ningún ítem de este sprint coincide.")
            if not sprint_items(backlog, number):
                io.say("El sprint quedó vacío. No se ejecutó nada.")
                return
            continue
        io.say("No se ejecutó nada.")
        return

    pending = [i for i in sprint_items(backlog, number) if i["status"] != "done"]
    for item in pending:
        item["status"] = "in_progress"
    session.save()
    outcome = run_act(
        runtime,
        sprint_request(session.request, backlog, number),
        io=io,
        confirm_switch=confirm_switch,
        stories_preapproved=True,
    )
    final = "done" if outcome.status in DONE_OUTCOMES else (
        "in_progress" if outcome.status in STARTED_OUTCOMES else "pending"
    )
    for item in pending:
        item["status"] = final
    session.save()
    if final == "done":
        io.say(f"Sprint {number} terminado. Probalo; /testing corre las pruebas y /do sigue con el próximo.")
    elif final == "in_progress":
        io.say(f"Sprint {number} quedó en curso: revisá la rama y commiteá o repetí /do sprint {number}.")
    else:
        io.say(f"Sprint {number} no se ejecutó ({outcome.status}).")


def cmd_do(
    session: CommandSession,
    runtime: ProviderRuntime,
    argument: str,
    *,
    io: ConsoleIO,
    confirm_switch: Confirm,
) -> None:
    session.load()
    if session.plan is None and session.backlog is None:
        if session.load_snapshot() is not None:
            io.say("El plan guardado es de una sesión anterior: volvé a correr /plan para ejecutarlo.")
        else:
            io.say(f"{NO_PLAN} Primero /plan y aprobalo.")
        return
    if not session.agreed:
        io.say("El plan no está acordado. Aprobalo con /plan antes de /do.")
        return
    if session.backlog is not None:
        _do_sprint(session, runtime, argument, io=io, confirm_switch=confirm_switch)
        return

    plan = session.plan
    assert plan is not None
    if argument.strip():
        io.say("Este plan no usa Scrum: /do ejecuta el plan acordado completo (sin sprints).")
    io.say("Paso a ejecutar: el plan acordado completo.")
    for line in plan_summary(plan, runtime):
        io.say(line)
    if not io.confirm("¿Ejecutar este paso?"):
        io.say("No se ejecutó nada.")
        return
    outcome = run_act(
        runtime,
        plan.request,
        io=io,
        confirm_switch=confirm_switch,
        plan=plan,
    )
    if outcome.plan is not None:
        session.plan = outcome.plan
    session.save()
    if outcome.status in DONE_OUTCOMES | STARTED_OUTCOMES:
        io.say("Paso terminado. Probalo y usá /testing para correr las pruebas.")


def cmd_testing(
    session: CommandSession,
    runtime: ProviderRuntime,
    argument: str,
    *,
    io: ConsoleIO,
) -> None:
    session.load()
    target = argument.strip()
    has_plan = session.plan is not None or session.backlog is not None
    if not has_plan and not target:
        target = io.ask("No hay plan. ¿Qué querés probar? ")
        if not target:
            io.say("No se probó nada.")
            return
    if not target and session.backlog is not None:
        current = next_sprint(session.backlog)
        target = f"sprint {current}" if current else "el backlog completo"
    commands = list(runtime.project_config.workspace.test_commands)
    if not commands:
        io.say(
            "El proyecto no declara pruebas (workspace.test_commands en project.yaml). "
            "No se ejecutó nada."
        )
        return
    io.say(f"Pruebas de: {target or 'el plan acordado'}")
    root = runtime.workspace.root if runtime.workspace is not None else session.root
    timeout = runtime.project_config.workspace.command_timeout_seconds
    for command in commands:
        io.say(f"→ {command}")
        try:
            done = subprocess.run(
                _command_argv(command),
                shell=False,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            io.say("  FALLA: excedió el tiempo")
            continue
        except OSError as exc:
            io.say(f"  FALLA: no se pudo ejecutar ({exc})")
            continue
        state = "OK" if done.returncode == 0 else f"FALLA (exit {done.returncode})"
        io.say(f"  {state}")
        tail = ((done.stdout or "") + (done.stderr or "")).strip().splitlines()[-OUTPUT_TAIL_LINES:]
        for line in tail:
            io.say(f"    {line}")
    io.say("Solo se reportan resultados: no se corrigió nada.")


def run_direct_request(
    runtime: ProviderRuntime,
    request: str,
    *,
    io: ConsoleIO,
    confirm_switch: Confirm,
) -> None:
    """Pedido sin comando que Triage reconoció como cambio: plan → OK → ejecuta."""

    if not io.confirm("Esto es un pedido de cambio. ¿Lo planifico y lo ejecuto (con tu OK)?"):
        io.say("Quedó como conversación. No se planificó nada.")
        return
    run_act(runtime, request, io=io, confirm_switch=confirm_switch)
