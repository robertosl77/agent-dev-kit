"""Genera los assets de Claude a partir de las definiciones de Agent Dev Kit.

Fuente única de verdad: los *_BASE_INSTRUCTIONS / *_HANDOFF_DESCRIPTION de
src/agent_dev_kit/agents, el grafo permanente de routing.py y el mapa de
riesgos de orchestration_policy.py. No editar a mano los archivos generados.

Salidas:
  plugins/agent-dev-kit/            plugin de Claude Code (subagentes + skill orquestador)
  dist/claude-ai-skills/<skill>.zip skills para subir en claude.ai (uno por zip)

Uso:
  PYTHONPATH=src python scripts/build_claude_assets.py
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from agent_dev_kit import agents as adk_agents
from agent_dev_kit.commands import render_skill_section
from agent_dev_kit.orchestration_policy import RISK_REQUIRED_AGENTS
from agent_dev_kit.routing import DEFAULT_CAPABILITY_GRAPH

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins" / "agent-dev-kit"
DIST_DIR = ROOT / "dist" / "claude-ai-skills"
PREFIX = "adk"

# Orden del catálogo (docs/catalogo_agentes.md).
AGENT_KEYS = (
    "triage", "product", "pmo", "scrum_master", "architecture", "ux_ui",
    "backend", "frontend", "database", "security", "testing", "reviewer",
    "documentation", "devops", "performance", "observability", "data",
)

# Roles de definición/gobierno/revisión: no escriben código (catálogo, "límites").
READ_ONLY_ROLES = {"product", "pmo", "scrum_master", "architecture", "reviewer"}

LANGUAGE_RULE = (
    "Respond in the same language the person uses (Spanish by default for this team)."
)

HUMAN_QA_RULE = "Final functional acceptance (human QA) always remains human."


def slug(key: str) -> str:
    return f"{PREFIX}-{key.replace('_', '-')}"


def definition(key: str):
    return getattr(adk_agents, f"build_{key}_definition")()


def neighbors(key: str) -> tuple[str, ...]:
    return tuple(t for t in DEFAULT_CAPABILITY_GRAPH.get(key, ()) if t != "triage")


def graph_block() -> str:
    lines = []
    for key in AGENT_KEYS:
        if key == "triage":
            continue
        targets = ", ".join(slug(t) for t in neighbors(key)) or "(none)"
        lines.append(f"- {slug(key)} -> {targets}")
    return "\n".join(lines)


def risk_block() -> str:
    return "\n".join(
        f"- {risk} -> {', '.join(slug(a) for a in agents)}"
        for risk, agents in RISK_REQUIRED_AGENTS.items()
    )


def catalog_block() -> str:
    return "\n".join(
        f"- {slug(k)}: {definition(k).handoff_description}"
        for k in AGENT_KEYS
        if k != "triage"
    )


ORCHESTRATION_RULES = """## Orchestration procedure

1. Classify the request (feature, defect, incident, operational, security,
   performance, documentation). Apply your Triage rules above.
2. Detect risk flags and derive the REQUIRED specialists with the risk map.
   A required specialist can never be skipped or replaced by another one.
3. Build the execution DAG: nodes = (id, specialist, objective, depends_on).
   Every edge must exist in the capability graph. Prefer the smallest DAG
   that covers every required specialist. Durable work ends in
   Reviewer and, when it changes knowledge, Documentation.
4. Show the DAG to the person as a compact diagram + table and WAIT for
   approval before executing anything.
5. Execute ready nodes in dependency order. Pass to each node only the
   relevant outputs of its predecessors (minimal context loss).
6. If a node reports a blocker, a missing decision or a domain change,
   stop, re-plan the affected part of the DAG and tell the person.
7. Close with a summary: nodes executed, decisions, evidence (tests, review)
   and what remains for human QA.
8. Record the orchestration trace (see "Orchestration trace") when the plan
   is shown, when it is approved/changed, and at the end.

## Hard rules

- Never do specialized work yourself when a specialist owns it.
- Never invent a role that is not in the catalog; surface the limitation.
- Git: never work on main/master; branches are created from the
  integration branch and only after the person approves the plan.
"""


TRACE_SCHEMA = """## Orchestration trace

Same record as the Agent Dev Kit runtime (`OrchestrationTrace`), so the
decision can be audited later with `graph_analysis.py`. One JSON object:

```json
{
  "run_id": "adk-YYYYMMDD-HHMMSS",
  "recorded_at": "ISO-8601 timestamp",
  "host": "HOST_NAME",
  "mode": "propose | act",
  "status": "planned | approved | done | blocked",
  "agreed": false,
  "request_summary": "one line",
  "full_request": "the request as written by the person",
  "classification": "feature | defect | incident | operational | security | performance | documentation",
  "risk_flags": ["flag from the risk map", "..."],
  "durable_artifacts": ["functional_spec | technical_spec | adr | ..."],
  "agent_decisions": [
    {"agent": "backend", "decision": "required | included | excluded", "reason": "why"}
  ],
  "dag": [
    {"id": "n1", "agent": "architecture", "objective": "...", "depends_on": [], "status": "pending | done | blocked"}
  ],
  "backlog": [
    {"id": "HU-01", "type": "RF | RNF", "title": "...", "criteria": ["..."], "sprint": 1, "status": "pending | in_progress | done"}
  ],
  "definition_of_done": ["cross-cutting RNF that every item must meet"],
  "handoffs": 0,
  "revisits": 0,
  "human_overrides": ["what the person changed in the plan, verbatim"],
  "notes": "re-plans, blockers, limitations"
}
```

Rules:
- `agent_decisions` lists ALL 16 specialists, also the excluded ones, each
  with a concrete reason. This is what makes the routing auditable.
- Agent keys use the runtime form (`ux_ui`, `scrum_master`), not `adk-` names.
- Never put secrets, credentials or personal data in the trace.
- Do not invent metrics you cannot observe (tokens, durations, model calls).
- `agreed` is true only after the person approves the whole plan; a re-plan
  sets it back to false.
- `backlog` is empty for small requests without Scrum; `sprint` is null there.
"""


def orchestrator_body(*, execution: str, host: str, persistence: str) -> str:
    triage = definition("triage")
    return f"""# Agent Dev Kit — Orchestrator (Triage + Planner)

{triage.instructions.strip()}

{ORCHESTRATION_RULES}
{render_skill_section()}

## Execution in this environment

{execution}

{TRACE_SCHEMA.replace("HOST_NAME", host)}
### Where the trace is stored here

{persistence}

## Specialist catalog

{catalog_block()}

## Capability graph (allowed handoffs)

{graph_block()}

## Risk map (risk flag -> required specialists)

{risk_block()}

{HUMAN_QA_RULE}
{LANGUAGE_RULE}
"""


# --------------------------------------------------------------------------
# Claude Code plugin
# --------------------------------------------------------------------------

CODE_EXECUTION = """Each specialist is a Claude Code subagent of this plugin, named
`agent-dev-kit:<specialist>` (for example `agent-dev-kit:adk-backend`).
Delegate every DAG node to its subagent with the Agent tool. Run nodes
sequentially unless they are independent. Specialists may consult a direct
neighbor of the capability graph themselves; you remain the owner of the DAG
and of the final trace."""

CODE_TRACE = """Append the trace as ONE line of compact JSON (JSONL) to
`.agent-dev-kit/runtime/orchestration-traces.jsonl` in the repository root
(create the folder if missing; never commit it, and warn the person if it is not git-ignored). Append a new line at each
status change (planned, approved, done/blocked) with the same `run_id`; never
rewrite previous lines. Mention the file path in your final summary."""


def write_plugin() -> None:
    if PLUGIN_DIR.exists():
        shutil.rmtree(PLUGIN_DIR)
    (PLUGIN_DIR / ".claude-plugin").mkdir(parents=True)
    (PLUGIN_DIR / "agents").mkdir()
    skill_dir = PLUGIN_DIR / "skills" / "orquestar"
    skill_dir.mkdir(parents=True)

    (PLUGIN_DIR / ".claude-plugin" / "plugin.json").write_text(
        '{\n'
        '  "name": "agent-dev-kit",\n'
        '  "description": "Equipo de 16 especialistas de Agent Dev Kit + orquestador (Triage) como subagentes de Claude Code.",\n'
        '  "version": "0.1.0",\n'
        '  "author": { "name": "Roberto Sanchez Leiva" }\n'
        '}\n',
        encoding="utf-8",
    )

    skill_dir.joinpath("SKILL.md").write_text(
        "---\n"
        "name: orquestar\n"
        "description: "
        + json.dumps(
            "Orquestador de Agent Dev Kit. Usar para cualquier pedido de desarrollo "
            "que deba repartirse entre especialistas: clasifica, arma el DAG de agentes, "
            "lo hace aprobar y lo ejecuta con los subagentes adk-*.",
            ensure_ascii=False,
        )
        + "\n"
        "---\n\n" + orchestrator_body(
            execution=CODE_EXECUTION, host="claude-code", persistence=CODE_TRACE
        ),
        encoding="utf-8",
    )

    for key in AGENT_KEYS:
        if key == "triage":
            continue
        d = definition(key)
        consults = ", ".join(f"agent-dev-kit:{slug(t)}" for t in neighbors(key))
        extra = ""
        if key in READ_ONLY_ROLES:
            extra = "disallowedTools: Edit, Write, NotebookEdit\n"
        body = f"""{d.instructions.strip()}

## Collaboration (Agent Dev Kit)

- You are one node of a DAG owned by the orchestrator (`/agent-dev-kit:orquestar`).
- You may consult directly ONLY these neighbors: {consults}.
- Anything outside that list: report it as a handoff need in your result.
- Return: what you did, decisions, evidence, open questions, suggested next specialist.
- Never work on main/master.
- {HUMAN_QA_RULE}
- {LANGUAGE_RULE}
"""
        (PLUGIN_DIR / "agents" / f"{slug(key)}.md").write_text(
            f"---\nname: {slug(key)}\ndescription: {json.dumps(d.handoff_description, ensure_ascii=False)}\n{extra}---\n\n{body}",
            encoding="utf-8",
        )


# --------------------------------------------------------------------------
# claude.ai skills
# --------------------------------------------------------------------------

AI_EXECUTION = """You run inside a single Claude chat. The specialists are the other
`adk-*` skills. For each DAG node, load that specialist's skill and answer
strictly in its role, under a header `### [node-id] <specialist>`. Keep
roles separated: a specialist never takes decisions owned by another one;
when it needs a neighbor, the next node consults it. If the person enabled
only some skills, treat the missing ones as disabled (node = BLOCKED)."""

AI_TRACE = """Use code execution to write the trace as `adk-trace-<run_id>.json`
(pretty-printed JSON) and keep it updated at each status change (planned,
approved, done/blocked). At the end, deliver the file to the person as a
downloadable file. Also print a short trace block in the chat:

```
TRACE <run_id> · <status>
clasificación: ...
riesgos: ...
incluidos: agente (motivo), ...
excluidos: agente (motivo), ...
DAG: n1 agente -> n2 agente -> ...
```

Chats do not share files, so each run produces its own file; the person can
later merge them into one `.jsonl` for analysis."""


def write_ai_skills() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)
    staging = DIST_DIR / "_src"

    for key in AGENT_KEYS:
        name = slug(key)
        folder = staging / name
        folder.mkdir(parents=True)
        if key == "triage":
            description = (
                "Orquestador de Agent Dev Kit. Usar SIEMPRE primero ante un pedido de "
                "desarrollo de software: clasifica, arma el DAG de especialistas adk-*, "
                "lo hace aprobar y lo ejecuta rol por rol."
            )
            body = orchestrator_body(
                execution=AI_EXECUTION, host="claude-ai", persistence=AI_TRACE
            )
        else:
            d = definition(key)
            description = (
                f"Especialista {key.replace('_', ' ')} de Agent Dev Kit. Usar cuando el "
                f"orquestador adk-triage asigna un nodo a este rol. {d.handoff_description}"
            )
            consults = ", ".join(slug(t) for t in neighbors(key))
            body = f"""# Agent Dev Kit — {name}

{d.instructions.strip()}

## Collaboration (Agent Dev Kit)

- You act only when adk-triage assigns you a DAG node.
- Natural neighbors (capability graph): {consults}.
- Return: what you did, decisions, evidence, open questions, suggested next specialist.
- {HUMAN_QA_RULE}
- {LANGUAGE_RULE}
"""
        folder.joinpath("SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n\n{body}",
            encoding="utf-8",
        )
        with zipfile.ZipFile(DIST_DIR / f"{name}.zip", "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(folder / "SKILL.md", f"{name}/SKILL.md")

    shutil.rmtree(staging)


def main() -> None:
    write_plugin()
    write_ai_skills()
    print(f"Plugin: {PLUGIN_DIR.relative_to(ROOT)}")
    print(f"Skills claude.ai: {DIST_DIR.relative_to(ROOT)} ({len(AGENT_KEYS)} zips)")


if __name__ == "__main__":
    main()
