"""Catálogo único de comandos del orquestador.

Fuente única de verdad para:
  - la consola (`agent-dev-kit run`): parseo y `/help`;
  - el generador de skills (`scripts/build_claude_assets.py`): sección
    "Comandos" del skill adk-triage y del plugin de Claude Code.

Si se agrega o cambia un comando, se cambia acá y ambos lados quedan
sincronizados (tests/test_commands.py lo verifica).
"""

from __future__ import annotations

from dataclasses import dataclass

READ_ACK = "Leído"
NO_PLAN = "No hay plan."
NO_BACKLOG = "No hay backlog."


@dataclass(frozen=True, slots=True)
class Command:
    name: str
    usage: str
    summary: str
    rules: tuple[str, ...]


COMMANDS: tuple[Command, ...] = (
    Command(
        name="/input",
        usage="/input <texto o adjuntos>",
        summary=f"recibe información; responde solo «{READ_ACK}»",
        rules=(
            f"Respond with exactly «{READ_ACK}» and nothing else: no summary, no question, no opinion.",
            "Accumulate everything (text, attachments, images, audio) as context for the next command.",
            "Valid at any moment (before or during /plan, before /testing, even during /do).",
            "It never changes the plan state.",
        ),
    ),
    Command(
        name="/plan",
        usage="/plan [texto]",
        summary="analiza y discute requisitos, alcance, historias, criterios y pasos; no ejecuta",
        rules=(
            "Plan (or re-plan) with everything accumulated by /input. `/plan <texto>` adds that text "
            "as a detail, adjustment or order and plans in the same message.",
            "Triage picks the roles the request needs: a small request gets a short DAG; a large one "
            "(e.g. a new application) brings all analysis roles: pmo, scrum_master, product, architecture.",
            "When the work is large, scrum_master enforces Scrum: every item goes to the product backlog, "
            "split into coded user stories (HU-01, HU-02...), delivered in sprints. Each sprint ends in "
            "something the person can test.",
            "The backlog marks each item as RF (functional requirement, usually a user story) or RNF "
            "(non-functional). Cross-cutting RNF go to the Definition of Done; concrete RNF work is a "
            "technical backlog item.",
            "Output is text/documents only. FORBIDDEN: code, file changes, branches, executing nodes.",
            "When the person approves the whole plan, show the full backlog as a table and mark the plan "
            "as agreed. A later /plan sets it back to NOT agreed until approved again.",
        ),
    ),
    Command(
        name="/grafo",
        usage="/grafo",
        summary="devuelve el JSON completo del último plan (incluye el backlog); no ejecuta",
        rules=(
            "Return the complete JSON of the latest plan (the current trace), not a diff.",
            f"If there is no plan, answer only «{NO_PLAN}».",
            "It never executes anything nor changes the state.",
        ),
    ),
    Command(
        name="/backlog",
        usage="/backlog",
        summary="muestra solo la tabla del backlog: ítem, tipo RF/RNF, sprint, estado",
        rules=(
            "Show only the backlog table: item, type (RF/RNF), sprint, status (pending / in progress / done).",
            f"If there is no backlog, answer only «{NO_BACKLOG}».",
            "It never executes anything nor changes the state.",
        ),
    ),
    Command(
        name="/do",
        usage="/do [sprint N o nodo]",
        summary="ejecuta el plan acordado, un paso por vez (sprint o nodo), con tu OK",
        rules=(
            "Requires an agreed (approved) plan. Without it: execute nothing and say so.",
            "First show the step to execute (the next sprint, or the next node when there is no Scrum): "
            "its items/stories, criteria and what the person will be able to test. WAIT for OK.",
            "The person may adjust the step there (remove or add a story); record the change in the trace "
            "without re-planning everything.",
            "Execute only that step, then stop and say what to test. `/do sprint 3` or `/do n4` targets a "
            "specific step.",
            "Git: work only on a branch created from the integration branch, never on main/master.",
        ),
    ),
    Command(
        name="/testing",
        usage="/testing [qué probar]",
        summary="prepara y ejecuta pruebas del plan; reporta OK/FALLA; no corrige",
        rules=(
            "Test what the plan says: the current sprint/step, or the ones the person names.",
            "Without a plan, ask what to test and agree on it before running anything.",
            "Report each check as OK or FALLA with evidence. NEVER fix the product automatically.",
        ),
    ),
    Command(
        name="/help",
        usage="/help",
        summary="lista todos los comandos",
        rules=(
            "List ALL commands of this catalog with their usage, also when the person asks "
            "\"¿cuáles son tus comandos?\".",
        ),
    ),
)

COMMAND_NAMES: tuple[str, ...] = tuple(command.name for command in COMMANDS)

GENERAL_RULES: tuple[str, ...] = (
    "Commands are optional. A message without a command works as always: Triage classifies, "
    "proposes the plan, waits for approval and executes.",
    "The command is the FIRST word of the message. One command per message: `/input /do` means "
    "/input and the rest is text.",
    "An unknown command (e.g. /plna) executes nothing: answer with the list of valid commands.",
    "Update the orchestration trace at every state change.",
)


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    name: str | None
    argument: str
    unknown: bool = False


def parse_command(message: str) -> ParsedCommand:
    """Split a message into (command, argument) following the catalog rules."""

    text = message.strip()
    if not text.startswith("/"):
        return ParsedCommand(name=None, argument=text)
    parts = text.split(maxsplit=1)
    head = parts[0]
    rest = text[len(head):].lstrip(" \t").removeprefix("\n") if len(parts) > 1 else ""
    name = head.lower()
    if name in COMMAND_NAMES:
        return ParsedCommand(name=name, argument=rest.strip())
    return ParsedCommand(name=name, argument=rest.strip(), unknown=True)


def render_help(*, extra: tuple[tuple[str, str], ...] = ()) -> str:
    """Help text shared by the console; `extra` adds host-only lines (/exit)."""

    rows = [(command.usage, command.summary) for command in COMMANDS] + list(extra)
    width = max(len(usage) for usage, _ in rows)
    lines = ["Comandos:"]
    lines += [f"  {usage.ljust(width)}  {summary}" for usage, summary in rows]
    lines.append("Sin comando: funciona como siempre (conversación / pedido directo).")
    return "\n".join(lines)


def render_skill_section() -> str:
    """Markdown block inserted in the orchestrator skill (claude.ai and Claude Code)."""

    out = ["## Commands", ""]
    out.append("| Command | What it does |")
    out.append("|---|---|")
    for command in COMMANDS:
        out.append(f"| `{command.usage}` | {command.summary} |")
    out.append("")
    out.append("General rules:")
    out += [f"- {rule}" for rule in GENERAL_RULES]
    for command in COMMANDS:
        out.append("")
        out.append(f"### `{command.name}`")
        out += [f"- {rule}" for rule in command.rules]
    out.append("")
    out.append(
        "State: SIN PLAN → /plan → PLANIFICANDO → (approval) → PLAN ACORDADO → /do → "
        "EJECUTANDO (one step) → stop for testing/approval → next /do. /input never changes the state."
    )
    return "\n".join(out)
