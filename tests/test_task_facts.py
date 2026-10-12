"""Golden case T-066 (M-085): facts before the node, verdict checks after it.

Reproduces the /task that kept answering "all criteria OK": the README was
written from project.yaml, while criterion 5 points to the project's task
rules. Runs offline with a scripted Anthropic client: no tokens.
"""

import io
import subprocess
from types import SimpleNamespace

import pytest

pytest.importorskip("anthropic")

from agent_dev_kit.console_modes import ConsoleIO, run_propose
from agent_dev_kit.execution import ProviderRuntime
from agent_dev_kit.project_config import load_project_config
from agent_dev_kit.provider_registry import ProviderRegistry
from agent_dev_kit.providers.provider_anthropic import AnthropicProvider
from agent_dev_kit.task_facts import TaskFacts, extract_criteria, verify_verdict
from agent_dev_kit.workspace_tools import Workspace

# Body of LibreriaIngles issue #117 (T-066), as GitHub returns it.
ISSUE_117 = """#117 [open] T-066 — Actualizar README: rama de desarrollo vigente y flujo de ramas

**Prioridad:** P3 — Baja / documentación
**Relación:** T-012 (documentación actual vs histórica), T-013 (instalación y flujo de ramas)

## Problema

El `README.md` de `develop` todavía indica:

```text
Rama de desarrollo actual
fix/mvp-funcional (sobre feat/mvp-foundation-v0.1)
```

## Criterios de aceptación

- El README identifica a `develop` como rama de integración/desarrollo.
- Aclara que las tareas se implementan en ramas específicas creadas desde `develop`.
- Mantiene que `main` no se modifica directamente durante el desarrollo.
- Evita referencias a ramas históricas como `fix/mvp-funcional` o `feat/mvp-foundation-v0.1` salvo que se conserven explícitamente como historia.
- El texto queda alineado con la regla de ramas documentada actualmente en las tareas del proyecto.

## Alcance

Solo corrección documental. No requiere cambios funcionales ni de código.
"""

README = """# Demo

| `develop` | Rama de **integración**. |

Cada tarea se trabaja en una rama creada a partir de `develop`.
Ejemplos: `feat/T-042-crud-libros`.
Guía: `docs/guia.md`.
"""

TAREAS = """# Tareas

Flujo vigente: **`develop` es la rama de integración** y **solo Roberto pasa `develop` → `main`**.
"""

PROJECT_YAML = """project:
  name: Demo
provider:
  name: anthropic
  default_model: claude-test
git_workflow:
  branches: {production: main, integration: develop}
  protected: [main, develop]
context:
  rule_sources:
    git_workflow: "docs/tareas.md#Regla de ramas"
agents:
  enabled: [triage, documentation, pmo]
"""

PLAN = {
    "request": "T-066",
    "profile": {
        "summary": "Analizar README para T-066.",
        "classification": "documentation",
        "risk_flags": [],
        "durable_artifacts": [],
    },
    "agent_decisions": [
        {"agent": "documentation", "selected": True, "gate": "docs", "reason": "README"},
        {"agent": "pmo", "selected": False, "gate": "not_needed", "reason": "Sin backlog"},
    ],
    "required_disabled_agents": [],
    "notes": None,
    "nodes": [
        {
            "id": "doc-analysis",
            "agent": "documentation",
            "phase": "analysis",
            "objective": "Analizar README vs issue #117",
            "depends_on": [],
        }
    ],
}

# What the model answered in the real runs: CA-5 "OK" citing the README.
NODE_ANSWER = """Informe T-066
[OK] CA-1 | README.md:3 | "Rama de **integración**"
[OK] CA-2 | README.md:5 | "texto que no está en el README"
[PENDIENTE] CA-4 | - | revisar ramas históricas
[OK] CA-5 | README.md:3 | "Rama de **integración**"
"""


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


class IssueWorkspace(Workspace):
    def read_issue(self, args):
        return ISSUE_117


def usage():
    return SimpleNamespace(
        input_tokens=10, output_tokens=5,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )


def msg(*blocks, stop="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop, usage=usage(), model="claude-test")


class Scripted:
    def __init__(self, answer=NODE_ANSWER):
        self.calls = []
        self.answer = answer

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("tool_choice", {}).get("name") == "submit_output":
            return msg(
                SimpleNamespace(type="tool_use", id="p1", name="submit_output", input=PLAN),
                stop="tool_use",
            )
        return msg(SimpleNamespace(type="text", text=self.answer))


@pytest.fixture
def project(tmp_path):
    root = tmp_path
    git(root, "init", "-q", "-b", "develop")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / "README.md").write_text(README, encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "tareas.md").write_text(TAREAS, encoding="utf-8")
    (root / "docs" / "guia.md").write_text("guía\n", encoding="utf-8")
    (root / ".agent-dev-kit").mkdir()
    (root / ".agent-dev-kit" / "project.yaml").write_text(PROJECT_YAML, encoding="utf-8")
    (root / ".gitignore").write_text(".agent-dev-kit/runtime/\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    git(root, "branch", "main")
    return root


def run(root, scripted, *answers):
    registry = ProviderRegistry()
    registry.register(
        "anthropic",
        lambda config: AnthropicProvider(
            default_model=config.default_model,
            client=SimpleNamespace(messages=scripted),
        ),
    )
    config = load_project_config(root)
    runtime = ProviderRuntime(
        registry=registry,
        project_config=config,
        workspace=IssueWorkspace(root, config.workspace),
        mode="propose",
    )
    out = io.StringIO()
    queue = list(answers)
    console = ConsoleIO(input_fn=lambda prompt: queue.pop(0), out=out)
    result = run_propose(
        runtime,
        "Analizá la issue #117 / T-066 en solo lectura: qué cambiar en README.md.",
        io=console,
        confirm_switch=lambda *args: False,
    )
    return result, out.getvalue()


def test_criteria_are_extracted_from_the_real_issue_body():
    criteria = extract_criteria(ISSUE_117)

    assert [item.id for item in criteria] == ["CA-1", "CA-2", "CA-3", "CA-4", "CA-5"]
    assert [item.rule_bound for item in criteria] == [False, False, False, False, True]


def test_node_gets_verified_facts_and_no_handoff_tools(project):
    scripted = Scripted()
    run(project, scripted)

    node_call = scripted.calls[1]
    prompt = node_call["messages"][0]["content"][0]["text"]
    assert "Current branch: develop" in prompt
    assert "git_workflow: docs/tareas.md#Regla de ramas" in prompt
    assert "CA-5: El texto queda alineado" in prompt
    assert "evaluate against the rule source (docs/tareas.md)" in prompt
    assert "feat/T-042-crud-libros (README.md:6)" in prompt
    assert "docs/guia.md (" not in prompt  # a file path is not a branch
    assert "delivered to the person as the final result" in prompt
    assert "[OK] CA-n | path:line" in prompt
    tools = {item["name"] for item in node_call["tools"]}
    assert not any(name.startswith("transfer_to_") for name in tools)
    system = node_call["system"][0]["text"]
    assert "Project rule sources" in system
    assert "not verified GitHub settings" in system


def test_wrong_source_and_bad_quotes_are_downgraded_in_code(project):
    result, out = run(project, Scripted())

    output = result.nodes[0].output
    assert '[OK] CA-1 | README.md:3' in output
    assert "[PENDIENTE] CA-2" in output and "la cita no está en README.md:5" in output
    assert "[PENDIENTE] CA-5" in output
    assert "CA-5 se evalúa contra docs/tareas.md" in output
    assert "[PENDIENTE] CA-3 | - | el agente no lo evaluó (control)" in output
    assert "Control de Agent Dev Kit" in output
    assert "Control de Agent Dev Kit" in out


def test_rule_bound_criterion_citing_the_rule_source_stays_ok(project):
    answer = (
        '[OK] CA-5 | docs/tareas.md:3 | "solo Roberto pasa `develop` → `main`"\n'
        '[PENDIENTE] CA-1 | - | x\n[PENDIENTE] CA-2 | - | x\n'
        '[PENDIENTE] CA-3 | - | x\n[PENDIENTE] CA-4 | - | x\n'
    )
    result, _ = run(project, Scripted(answer))

    output = result.nodes[0].output
    assert output.startswith("[OK] CA-5 | docs/tareas.md:3")
    assert "Control de Agent Dev Kit" not in output


def test_task_on_a_feature_branch_asks_before_spending(project):
    git(project, "checkout", "-q", "-b", "feat/t-220-otra")
    scripted = Scripted()

    result, out = run(project, scripted, "n")

    assert result is None
    assert scripted.calls == []
    assert "Estás en la rama 'feat/t-220-otra', no en 'develop'" in out


def test_verify_verdict_never_upgrades_and_ignores_free_text(tmp_path):
    facts = TaskFacts(criteria=extract_criteria(ISSUE_117))
    text = "Sin formato de veredicto.\n[PENDIENTE] CA-1 | - | falta"

    output, notes = verify_verdict(text, facts, Workspace(tmp_path))

    assert "[OK]" not in output
    assert len(notes) == 4  # CA-2..CA-5 were not evaluated
