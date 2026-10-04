from collections.abc import Iterable


DEFAULT_CAPABILITY_GRAPH: dict[str, tuple[str, ...]] = {
    "triage": (
        "product", "pmo", "architecture", "ux_ui", "backend", "frontend",
        "database", "security", "testing", "reviewer", "documentation",
        "devops", "performance", "observability", "data",
    ),
    "product": ("pmo", "architecture", "ux_ui", "documentation", "triage"),
    "pmo": ("product", "architecture", "reviewer", "documentation", "triage"),
    "architecture": (
        "backend", "frontend", "database", "security", "devops",
        "performance", "observability", "data", "testing",
        "documentation", "triage",
    ),
    "ux_ui": ("frontend", "testing", "reviewer", "documentation", "triage"),
    "backend": (
        "database", "frontend", "security", "testing", "performance",
        "observability", "reviewer", "documentation", "triage",
    ),
    "frontend": (
        "backend", "ux_ui", "security", "testing", "performance",
        "observability", "reviewer", "documentation", "triage",
    ),
    "database": (
        "backend", "data", "security", "testing", "performance",
        "observability", "reviewer", "documentation", "triage",
    ),
    "security": (
        "backend", "frontend", "database", "devops", "testing",
        "reviewer", "documentation", "triage",
    ),
    "testing": (
        "backend", "frontend", "database", "security", "performance",
        "reviewer", "documentation", "triage",
    ),
    "reviewer": (
        "product", "pmo", "architecture", "backend", "frontend",
        "database", "security", "testing", "documentation", "triage",
    ),
    "documentation": ("pmo", "triage"),
    "devops": (
        "backend", "security", "testing", "observability", "performance",
        "reviewer", "documentation", "triage",
    ),
    "performance": (
        "backend", "frontend", "database", "devops", "observability",
        "testing", "reviewer", "documentation", "triage",
    ),
    "observability": (
        "backend", "devops", "performance", "security",
        "reviewer", "documentation", "triage",
    ),
    "data": (
        "database", "backend", "security", "testing", "performance",
        "reviewer", "documentation", "triage",
    ),
}


def build_enabled_capability_graph(
    enabled_agents: Iterable[str],
) -> dict[str, tuple[str, ...]]:
    """Filter the permanent graph to the agents active in one project."""

    enabled = {normalize_agent_key(item) for item in enabled_agents}
    return {
        source: tuple(
            target
            for target in DEFAULT_CAPABILITY_GRAPH.get(source, ())
            if target in enabled
        )
        for source in enabled
    }


def normalize_agent_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")
