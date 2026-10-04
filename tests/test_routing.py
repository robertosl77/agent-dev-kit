from agent_dev_kit.routing import build_enabled_capability_graph


def test_capability_graph_keeps_natural_direct_handoffs():
    graph = build_enabled_capability_graph(
        ("triage", "architecture", "backend", "testing", "documentation")
    )

    assert graph["triage"] == (
        "architecture",
        "backend",
        "testing",
        "documentation",
    )
    assert "backend" in graph["architecture"]
    assert "testing" in graph["architecture"]
    assert "testing" in graph["backend"]
    assert "documentation" in graph["testing"]


def test_capability_graph_never_targets_disabled_agent():
    graph = build_enabled_capability_graph(
        ("triage", "frontend")
    )

    assert graph["triage"] == ("frontend",)
    assert "ux_ui" not in graph["frontend"]


def test_cross_cutting_role_handoffs_are_explicit():
    graph = build_enabled_capability_graph(
        (
            "product",
            "security",
            "observability",
            "data",
            "devops",
            "architecture",
            "pmo",
        )
    )

    assert "security" in graph["product"]
    assert "observability" in graph["product"]
    assert "data" in graph["security"]
    assert "observability" in graph["security"]
    assert "architecture" in graph["devops"]
    assert "pmo" in graph["observability"]
