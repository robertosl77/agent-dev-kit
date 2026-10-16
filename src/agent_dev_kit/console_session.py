"""Comandos de la consola interactiva (`agent-dev-kit run`).

Implementa el catálogo de `commands.py` sobre el runtime:

    /input    acumula contexto y responde «Leído»
    /plan     arma el plan (sin ejecutar), historias si aplica, y pide aprobarlo
    /grafo    JSON del último plan (con el backlog)
    /backlog  tabla del backlog (pasos del plan y su estado)
    /do       ejecuta el plan acordado, con tu OK, en una rama local
    /testing  corre los tests declarados del proyecto y reporta (no corrige)

El backlog se guarda en `.agent-dev-kit/runtime/backlog.json` para que
/backlog y /grafo sigan disponibles en otra sesión.

Límites actuales de la consola (los skills de claude.ai sí los cubren):
- el planner de Python no arma sprints: /do ejecuta el plan completo;
- un plan de una sesión anterior se puede ver (/grafo, /backlog) pero no
  ejecutar: hay que volver a correr /plan.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_dev_kit.commands import NO_BACKLOG, NO_PLAN, READ_ACK
from agent_dev_kit.console_modes import (
    Confirm,
    ConsoleIO,
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


@dataclass(slots=True)
class CommandSession:
    """Estado de una sesión de consola: contexto acumulado y plan vigente."""

    root: Path
    context: list[str] = field(default_factory=list)
    plan: TaskPlan | None = None
    agreed: bool = False

    # ------------------------------------------------------------ persistence
    @property
    def backlog_path(self) -> Path:
        return self.root / BACKLOG_FILE

    def snapshot(self) -> dict[str, Any] | None:
        plan = self.plan
        if plan is None:
            return self.load_snapshot()
        trace = plan.trace.to_dict() if plan.trace is not None else {}
        return {
            "request": plan.request,
            "agreed": self.agreed,
            "status": plan.execution_status,
            "backlog": [
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
    if argument.strip():
        session.context.append(argument.strip())
    request = session.request
    if not request:
        io.say("No hay nada para planificar: usá /input <texto> o /plan <texto>.")
        return

    # Re-plan: the previous agreement no longer holds (H2).
    session.agreed = False
    act_runtime = runtime if runtime.mode == "act" else runtime.with_mode("act")
    plan = _plan(act_runtime, request, confirm_switch)
    session.plan = plan
    for line in plan_summary(plan, act_runtime):
        io.say(line)

    workspace = runtime.workspace
    if plan.requires_story_approval and workspace is not None:
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
    io.say(format_usage_line(usage_stages(plan.trace), runtime.project_config.pricing))

    if io.confirm("¿Aprobás el plan" + (" y las historias?" if plan.requires_story_approval else "?")):
        session.agreed = True
        plan.story_approved = plan.requires_story_approval or plan.story_approved
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
    data = session.snapshot()
    items = (data or {}).get("backlog") or []
    if not items:
        io.say(NO_BACKLOG)
        return
    estado = "acordado" if data.get("agreed") else "no acordado"
    io.say(f"Backlog ({estado}):")
    io.say(f"  {'Paso':<10} {'Agente':<14} {'Estado':<10} Objetivo")
    for item in items:
        io.say(
            f"  {item['id']:<10} {item['agent']:<14} {item['status']:<10} {item['objective']}"
        )


def cmd_do(
    session: CommandSession,
    runtime: ProviderRuntime,
    argument: str,
    *,
    io: ConsoleIO,
    confirm_switch: Confirm,
) -> None:
    plan = session.plan
    if plan is None:
        if session.load_snapshot() is not None:
            io.say("El plan guardado es de una sesión anterior: volvé a correr /plan para ejecutarlo.")
        else:
            io.say(f"{NO_PLAN} Primero /plan y aprobalo.")
        return
    if not session.agreed:
        io.say("El plan no está acordado. Aprobalo con /plan antes de /do.")
        return
    if argument.strip():
        io.say(
            "En consola /do ejecuta el plan acordado completo; "
            "los pasos por sprint o por nodo están disponibles en los skills de claude.ai."
        )
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
    if outcome.status in {"committed", "not_committed", "no_changes"}:
        io.say("Paso terminado. Probalo y usá /testing para correr las pruebas.")


def cmd_testing(
    session: CommandSession,
    runtime: ProviderRuntime,
    argument: str,
    *,
    io: ConsoleIO,
) -> None:
    target = argument.strip()
    if session.plan is None and not target:
        target = io.ask("No hay plan. ¿Qué querés probar? ")
        if not target:
            io.say("No se probó nada.")
            return
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
