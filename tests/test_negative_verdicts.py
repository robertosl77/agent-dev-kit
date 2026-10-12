"""Regression of the real LibreriaIngles T-066 /task output.

No provider, model, GitHub credentials, or network is required.
"""
from types import SimpleNamespace

from agent_dev_kit.task_facts import (
    TaskFacts, build_facts, extract_criteria, verify_verdict, verdict_format_note,
)
from agent_dev_kit.workspace_tools import Workspace


ISSUE = """#117 T-066

## Criterios de aceptación

- El README identifica a `develop` como rama de integración/desarrollo.
- Aclara que las tareas se implementan en ramas específicas creadas desde `develop`.
- Mantiene que `main` no se modifica directamente durante el desarrollo.
- Evita referencias a ramas históricas como `fix/mvp-funcional` o `feat/mvp-foundation-v0.1` salvo que se conserven explícitamente como historia.
- El texto queda alineado con la regla de ramas documentada actualmente en las tareas del proyecto.

## Alcance
Sólo README.
"""

README = """# Flujo de ramas

`develop` es integración.
Cada tarea tiene una rama de `develop`.
No se permite escribir directamente en `main`.
"""

# Reproduction of the /task output that incorrectly approved CA-5 on project.yaml.
REAL_ANSWER = """[OK] CA-4 | README.md | ausencia comprobada de fix/mvp-funcional y feat/mvp-foundation-v0.1
[OK] CA-5 | README.md:3 | "Cada tarea tiene una rama de `develop`."

Conclusión: Los cinco criterios están cumplidos y se puede cerrar la issue.
"""


def example(tmp_path):
    (tmp_path / "README.md").write_text(README, encoding="utf-8")
    (tmp_path / ".agent-dev-kit").mkdir()
    (tmp_path / ".agent-dev-kit" / "project.yaml").write_text(
        "git_workflow:\n  branches: {integration: develop}\n",
        encoding="utf-8",
    )
    return Workspace(tmp_path)


def test_issue_parsing_identifies_negative_branch_evidence():
    items = extract_criteria(ISSUE)
    assert len(items) == 5
    assert items[3].absence_path == "README.md"
    assert items[3].absence_refs == (
        "fix/mvp-funcional", "feat/mvp-foundation-v0.1",
    )
    assert items[4].rule_bound
    assert items[0].absence_refs == ()


def test_code_accepts_verified_absence_without_quoting_missing_lines(tmp_path):
    workspace = example(tmp_path)
    facts = TaskFacts(criteria=extract_criteria(ISSUE))
    output, notes = verify_verdict(
        "[OK] CA-4 | README.md | ausencia comprobada de "
        "fix/mvp-funcional y feat/mvp-foundation-v0.1\n",
        facts, workspace,
    )
    assert "[OK] CA-4 | README.md" in output
    assert all("CA-4: OK" not in x for x in notes)
    assert "CA-4: OK → PENDIENTE" not in output
    # Other, unevaluated criteria are not silently promoted.
    assert "[PENDIENTE] CA-5" in output


def test_code_blocks_false_absence_if_historical_reference_is_present(tmp_path):
    workspace = example(tmp_path)
    (tmp_path / "README.md").write_text(
        README + "\n`fix/mvp-funcional` — rama antigua.\n",
        encoding="utf-8",
    )
    facts = TaskFacts(criteria=extract_criteria(ISSUE))
    output, notes = verify_verdict(
        "[OK] CA-4 | README.md | ausencia comprobada de "
        "fix/mvp-funcional y feat/mvp-foundation-v0.1", facts, workspace,
    )
    assert "[PENDIENTE] CA-4" in output
    assert "siguen presentes" in output
    assert any("CA-4: OK → PENDIENTE" in note for note in notes)


def test_negative_proof_requires_exact_document_and_both_references(tmp_path):
    workspace = example(tmp_path)
    facts = TaskFacts(criteria=extract_criteria(ISSUE))
    bad = [
        "[OK] CA-4 | docs/other.md | ausencia comprobada de fix/mvp-funcional y feat/mvp-foundation-v0.1",
        "[OK] CA-4 | README.md | ausencia comprobada de fix/mvp-funcional",
        "[OK] CA-4 | README.md | dice que cumple",
    ]
    for answer in bad:
        output, notes = verify_verdict(answer, facts, workspace)
        assert "[PENDIENTE] CA-4" in output
        assert any("CA-4: OK → PENDIENTE" in n for n in notes)


def test_rule_bound_ok_fails_closed_without_configured_authority(tmp_path):
    workspace = example(tmp_path)
    facts = TaskFacts(criteria=extract_criteria(ISSUE))
    output, notes = verify_verdict(REAL_ANSWER, facts, workspace)
    assert "[OK] CA-4" in output
    assert "[PENDIENTE] CA-5" in output
    assert "falta configurar context.rule_sources" in output
    assert "Veredicto global verificado: PENDIENTE (CA-5)" in output
    assert "No corresponde afirmar que todos los criterios se cumplen" in output
    assert any("CA-5: OK → PENDIENTE" in n for n in notes)


def test_rule_bound_verdict_with_authority_requires_real_citation(tmp_path):
    workspace = example(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "tareas.md").write_text(
        "Regla: sólo el dueño autoriza develop a main.\n",
        encoding="utf-8",
    )
    facts = TaskFacts(
        criteria=extract_criteria(ISSUE), rule_files=["docs/tareas.md"],
    )
    wrong, _ = verify_verdict(
        '[OK] CA-5 | README.md:3 | "Cada tarea tiene una rama de `develop`."',
        facts, workspace,
    )
    assert "[PENDIENTE] CA-5" in wrong
    correct, _ = verify_verdict(
        '[OK] CA-5 | docs/tareas.md:1 | "sólo el dueño autoriza develop a main."',
        facts, workspace,
    )
    assert "[OK] CA-5" in correct


def test_facts_prompt_explains_absence_and_missing_authority(tmp_path):
    workspace = example(tmp_path)
    workspace.read_issue = lambda data: ISSUE
    config = SimpleNamespace(rule_sources={})
    facts = build_facts(workspace, config, "Analizá issue #117")
    assert "Code verified absence in README.md" in facts.text
    assert "CA-4" in facts.text
    assert "context.rule_sources is NOT configured" in facts.text
    assert "MUST be PENDIENTE" in facts.text
    note = verdict_format_note(facts)
    assert "absence has no quotable line" in note
    assert "rule-bound criteria" in note


def test_unknown_negative_assertions_are_not_approved_automatically(tmp_path):
    workspace = example(tmp_path)
    facts = TaskFacts(criteria=extract_criteria(ISSUE))
    output, notes = verify_verdict(
        "[PENDIENTE] CA-4 | - | el modelo solicita revisar el contexto histórico",
        facts, workspace,
    )
    assert "[OK] CA-4" not in output
    assert all("CA-4: OK" not in n for n in notes)
