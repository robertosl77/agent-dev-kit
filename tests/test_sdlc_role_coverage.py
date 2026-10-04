from agent_dev_kit.agents.agent_devops import build_devops_definition
from agent_dev_kit.agents.agent_observability import build_observability_definition
from agent_dev_kit.agents.agent_product import build_product_definition
from agent_dev_kit.agents.agent_security import build_security_definition
from agent_dev_kit.agents.agent_testing import build_testing_definition
from agent_dev_kit.agents.agent_triage import build_triage_definition
from agent_dev_kit.agents.agent_ux_ui import build_ux_ui_definition


def text(builder):
    return builder().instructions.lower()


def test_product_owns_business_analysis_and_non_functional_constraints():
    value = text(build_product_definition)
    assert "business analysis" in value
    assert "accessibility" in value
    assert "privacy/compliance" in value
    assert "reliability" in value


def test_accessibility_is_split_between_ux_and_testing():
    ux = text(build_ux_ui_definition)
    testing = text(build_testing_definition)

    assert "wcag" in ux
    assert "accessibility" in testing
    assert "human/manual evaluation" in testing


def test_security_owns_privacy_technical_assurance_not_legal_advice():
    value = text(build_security_definition)

    assert "privacy engineering" in value
    assert "compliance" in value
    assert "legal advice" in value


def test_observability_covers_reliability_and_incident_management():
    value = text(build_observability_definition)

    assert "service level indicators" in value
    assert "service level objectives" in value
    assert "incident" in value
    assert "post-incident" in value


def test_devops_covers_platform_and_release_operations():
    value = text(build_devops_definition)

    assert "platform-engineering" in value
    assert "release operations" in value
    assert "rollback/recovery" in value


def test_triage_handles_incident_intake_without_becoming_diagnostician():
    value = text(build_triage_definition)

    assert "support reports and production incidents" in value
    assert "route diagnosis to observability" in value
    assert "do not diagnose" in value
