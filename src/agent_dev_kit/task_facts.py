"""Deterministic facts before a node and verdict checks after it (M-085).

The model interprets and writes; everything that can be checked with code is
resolved here, without tokens:

    before the node                      after the node
    ───────────────                      ──────────────
    current / integration branch         every [OK] line needs a citation
    branches known to the clone          the cited file exists and the
    the issue + its acceptance criteria    quote is on (or next to) that line
    criteria that refer to project rules a rule-bound criterion must cite
    the project's rule sources             the rule source, not another file
    branch names in the referenced       missing criteria are added as
      files that do not exist in git       [PENDIENTE]

The checks can only move a verdict from OK to PENDIENTE, never the reverse.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent_dev_kit.git_actions import current_branch, is_git_repository
from agent_dev_kit.workspace_tools import run_git

MAX_ISSUE_CHARS = 6000
MAX_BRANCHES = 60
MAX_UNVERIFIED = 20

_GITHUB_ISSUE = re.compile(r"#(\d+)\b")
_PATH = re.compile(r"(?<![\w/.-])((?:\.?[\w-]+/)*[\w.-]+\.(?:md|txt|ya?ml|rst|json|toml))\b")
_BRANCH_NAME = re.compile(
    r"(?<![\w/.-])((?:feat|feature|fix|bugfix|hotfix|chore|docs|refactor|test|"
    r"release|archivo|perf|ci|build|style)/[A-Za-z0-9._-]*[A-Za-z0-9])(?![\w/-])"
)
_FILE_LIKE = re.compile(r"\.(?:md|txt|rst|ya?ml|json|toml|py|ts|js|html|css|sql|png|jpe?g|svg)$", re.IGNORECASE)
_CRITERIA_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s*|\*\*)?\s*(criterios?\s+de\s+aceptaci[oó]n|acceptance\s+criteria)",
    re.IGNORECASE,
)
_HEADING = re.compile(r"^\s*(#{1,6}\s+\S|\*\*[^*]+\*\*\s*:?\s*$)")
_ITEM = re.compile(r"^\s*(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)(.+?)\s*$")
_RULE_WORDS = re.compile(
    r"\b(regla|reglas|rule|rules|pol[ií]tica|policy|documentad[oa]s?|"
    r"alinead[oa]|aligned|conforme|seg[uú]n\s+lo\s+documentado)\b",
    re.IGNORECASE,
)
_VERDICT_LINE = re.compile(
    r"^(?P<prefix>\s*(?:[-*]\s*)?)\[(?P<status>OK|PENDIENTE)\]\s*"
    r"(?P<item>[^|]+?)\s*\|\s*(?P<where>[^|]*?)\s*\|\s*(?P<rest>.*)$"
)
_LOCATION = re.compile(r"([\w./-]+\.\w+):(\d+)(?:\s*[-–]\s*(\d+))?")
_QUOTE = re.compile(r"[\"“«`']([^\"”»`']{4,})[\"”»`']")


@dataclass(frozen=True, slots=True)
class Criterion:
    id: str
    text: str
    rule_bound: bool


@dataclass(slots=True)
class TaskFacts:
    text: str = ""
    criteria: list[Criterion] = field(default_factory=list)
    rule_files: list[str] = field(default_factory=list)
    issue_number: int | None = None


# --------------------------------------------------------------- before


def build_facts(workspace: Any, config: Any, request: str) -> TaskFacts:
    """Collect verifiable facts once per task; never raises."""

    facts = TaskFacts()
    root: Path = workspace.root
    lines: list[str] = [
        "Facts resolved by Agent Dev Kit in code before this node (verified; "
        "do not fetch them again with tools):"
    ]

    git_ok = is_git_repository(root)
    branches: list[str] = []
    if git_ok:
        branch = current_branch(root)
        integration = config.git_workflow.integration_branch
        lines.append(
            f"- Current branch: {branch} (integration branch: {integration}). "
            "Files are read from the current branch."
        )
        branches = _branches(root)
        shown = branches[:MAX_BRANCHES]
        more = len(branches) - len(shown)
        lines.append(
            "- Branches known to this clone (last git fetch; not live GitHub): "
            + (", ".join(shown) or "(none)")
            + (f" … (+{more})" if more > 0 else "")
        )

    rule_sources: Mapping[str, str] = getattr(config, "rule_sources", {}) or {}
    if rule_sources:
        lines.append(
            "- Project rule sources (authoritative documents for these topics; "
            "project.yaml only holds the subset the framework enforces in code):"
        )
        for topic, target in rule_sources.items():
            path = target.split("#", 1)[0].strip()
            exists = (root / path).is_file()
            facts.rule_files.append(path)
            lines.append(
                f"  - {topic}: {target}" + ("" if exists else " (NOT FOUND in the repo)")
            )
    lines.append(
        "- Branch protections or any other live GitHub setting cannot be "
        "verified with the available tools: a document that states them as "
        "fact states declared policy, not verified state."
    )

    issue_text = _issue_text(workspace, request, facts)
    if issue_text:
        lines.append("- Issue (already read for you):")
        lines.append(_indent(issue_text))
        facts.criteria = extract_criteria(issue_text)
    if facts.criteria:
        lines.append("- Acceptance criteria extracted from the issue:")
        for item in facts.criteria:
            bound = (
                " [refers to project rules: evaluate against the rule source"
                + (f" ({', '.join(facts.rule_files)})" if facts.rule_files else "")
                + " and cite it]"
                if item.rule_bound
                else ""
            )
            lines.append(f"  - {item.id}: {item.text}{bound}")

    if git_ok:
        unverified = unverified_branch_names(
            workspace, referenced_files(workspace, request + "\n" + issue_text), branches
        )
        if unverified:
            lines.append(
                "- Branch names written in the referenced files that do not "
                "exist in git (invented or historical; report each one):"
            )
            lines.extend(f"  - {name} ({where})" for name, where in unverified)

    facts.text = "\n".join(lines) + "\n\n"
    return facts


def extract_criteria(issue_text: str) -> list[Criterion]:
    """Numbered/bulleted items under an 'acceptance criteria' heading."""

    criteria: list[Criterion] = []
    inside = False
    for raw in issue_text.splitlines():
        if _CRITERIA_HEADING.match(raw):
            inside = True
            continue
        if not inside:
            continue
        if _HEADING.match(raw) and not _ITEM.match(raw):
            break
        item = _ITEM.match(raw)
        if item:
            text = " ".join(item.group(1).split())
            criteria.append(
                Criterion(
                    id=f"CA-{len(criteria) + 1}",
                    text=text,
                    rule_bound=bool(_RULE_WORDS.search(text)),
                )
            )
    return criteria


def referenced_files(workspace: Any, text: str) -> list[str]:
    found: list[str] = []
    for match in _PATH.finditer(text):
        candidate = match.group(1).lstrip("./") if match.group(1).startswith("./") else match.group(1)
        if candidate.startswith(".agent-dev-kit/runtime"):
            continue
        if (workspace.root / candidate).is_file() and candidate not in found:
            found.append(candidate)
    return found


def unverified_branch_names(
    workspace: Any,
    files: Sequence[str],
    branches: Sequence[str],
) -> list[tuple[str, str]]:
    known = {name.split("/", 1)[1] if name.startswith("origin/") else name for name in branches}
    known_lower = {name.lower() for name in known}
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for rel in files:
        if rel.endswith((".yaml", ".yml")):
            continue
        try:
            content = (workspace.root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(content.splitlines(), start=1):
            for match in _BRANCH_NAME.finditer(line):
                name = match.group(1)
                if name.lower() in known_lower or name in seen:
                    continue
                if _FILE_LIKE.search(name) or (workspace.root / name).exists():
                    continue  # a path such as docs/guide.md, not a branch
                seen.add(name)
                result.append((name, f"{rel}:{number}"))
                if len(result) >= MAX_UNVERIFIED:
                    return result
    return result


# ---------------------------------------------------------------- after


def verdict_format_note(facts: TaskFacts) -> str:
    """Exact line format the post-check can verify (only when there are criteria)."""

    if not facts.criteria:
        return ""
    ids = ", ".join(item.id for item in facts.criteria)
    return (
        "Verdict format (checked by code after you answer): for each criterion "
        f"({ids}) write exactly one line\n"
        "[OK] CA-n | path:line | \"exact text copied from that line\"\n"
        "[PENDIENTE] CA-n | path:line or - | what is missing\n"
        "An [OK] whose quote is not on that line of that file is turned into "
        "[PENDIENTE] automatically. Several citations: separate them with ';'.\n\n"
    )


def verify_verdict(output: str, facts: TaskFacts, workspace: Any) -> tuple[str, list[str]]:
    """Downgrade unverifiable [OK] lines; add criteria the node skipped."""

    if not output or not facts.criteria:
        return output, []
    by_id = {item.id: item for item in facts.criteria}
    notes: list[str] = []
    seen: set[str] = set()
    lines = output.splitlines()
    for index, line in enumerate(lines):
        match = _VERDICT_LINE.match(line)
        if not match:
            continue
        item_id = _criterion_id(match.group("item"))
        if item_id:
            seen.add(item_id)
        if match.group("status") != "OK":
            continue
        problem = _citation_problem(
            match.group("where"),
            match.group("rest"),
            by_id.get(item_id) if item_id else None,
            facts,
            workspace,
        )
        if problem:
            lines[index] = (
                f"{match.group('prefix')}[PENDIENTE] {match.group('item').strip()} | "
                f"{match.group('where').strip()} | {match.group('rest').strip()} "
                f"(control: {problem})"
            )
            notes.append(f"{item_id or match.group('item').strip()}: OK → PENDIENTE ({problem})")
    for item in facts.criteria:
        if item.id not in seen:
            lines.append(f"[PENDIENTE] {item.id} | - | el agente no lo evaluó (control)")
            notes.append(f"{item.id}: sin evaluar → PENDIENTE")
    if notes:
        lines += ["", "Control de Agent Dev Kit (código, sin tokens):"]
        lines += [f"- {note}" for note in notes]
    return "\n".join(lines), notes


def _citation_problem(
    where: str,
    rest: str,
    criterion: Criterion | None,
    facts: TaskFacts,
    workspace: Any,
) -> str | None:
    locations = _LOCATION.findall(where)
    if not locations:
        return "sin cita archivo:línea"
    quotes = _QUOTE.findall(rest) or [rest]
    cited_files: list[str] = []
    for path, start, end in locations:
        cited_files.append(path)
        problem = _quote_problem(workspace, path, int(start), int(end or start), quotes)
        if problem:
            return problem
    if criterion is not None and criterion.rule_bound and facts.rule_files:
        if not any(_same_path(path, rule) for path in cited_files for rule in facts.rule_files):
            return (
                f"{criterion.id} se evalúa contra {', '.join(facts.rule_files)}; "
                "la cita no es de esa fuente"
            )
    return None


def _quote_problem(workspace: Any, path: str, start: int, end: int, quotes: Sequence[str]) -> str | None:
    try:
        target = workspace.resolve(path)
    except Exception:  # outside the project or forbidden
        return f"{path} no es un archivo legible del proyecto"
    if not target.is_file():
        return f"{path} no existe"
    content = target.read_text(encoding="utf-8", errors="replace").splitlines()
    window = content[max(start - 3, 0): end + 2]
    haystack = _normalize(" ".join(window))
    for quote in quotes:
        needle = _normalize(quote)
        if len(needle) >= 4 and needle in haystack:
            return None
    return f"la cita no está en {path}:{start}"


def _criterion_id(item: str) -> str | None:
    match = re.search(r"\bCA-?\s*(\d+)\b", item, re.IGNORECASE)
    return f"CA-{int(match.group(1))}" if match else None


def _same_path(cited: str, rule: str) -> bool:
    cited, rule = cited.strip("./"), rule.strip("./")
    return cited == rule or cited.endswith("/" + rule) or rule.endswith("/" + cited)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[*_`|>#]", " ", text)
    text = text.replace("“", '"').replace("”", '"')
    return " ".join(text.split())


# --------------------------------------------------------------- helpers


def _branches(root: Path) -> list[str]:
    completed = run_git(root, ["branch", "--all", "--format=%(refname:short)"])
    if completed.returncode != 0:
        return []
    return [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip() and not line.strip().endswith("/HEAD") and line.strip() != "origin"
    ]


def _issue_text(workspace: Any, request: str, facts: TaskFacts) -> str:
    match = _GITHUB_ISSUE.search(request)
    if not match:
        return ""
    facts.issue_number = int(match.group(1))
    try:
        text = workspace.read_issue({"number": facts.issue_number})
    except Exception as exc:  # network, private repo, no origin: the agent can still try
        return f"(could not read issue #{facts.issue_number}: {exc})"
    return text if len(text) <= MAX_ISSUE_CHARS else text[:MAX_ISSUE_CHARS] + "\n... (truncated)"


def _indent(text: str) -> str:
    return "\n".join("    " + line for line in text.splitlines())
