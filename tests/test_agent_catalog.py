from agent_dev_kit.agents import (
    build_architecture_definition,
    build_backend_definition,
    build_data_definition,
    build_database_definition,
    build_devops_definition,
    build_documentation_definition,
    build_frontend_definition,
    build_observability_definition,
    build_performance_definition,
    build_pmo_definition,
    build_product_definition,
    build_reviewer_definition,
    build_security_definition,
    build_testing_definition,
    build_triage_definition,
    build_ux_ui_definition,
)


BUILDERS = (
    build_product_definition,
    build_pmo_definition,
    build_architecture_definition,
    build_ux_ui_definition,
    build_backend_definition,
    build_frontend_definition,
    build_database_definition,
    build_security_definition,
    build_testing_definition,
    build_reviewer_definition,
    build_documentation_definition,
    build_triage_definition,
    build_devops_definition,
    build_performance_definition,
    build_observability_definition,
    build_data_definition,
)


def test_catalog_has_all_sixteen_agents():
    definitions = [builder() for builder in BUILDERS]

    assert len(definitions) == 16
    assert len({definition.name for definition in definitions}) == 16


def test_all_catalog_agents_have_handoff_description():
    assert all(builder().handoff_description for builder in BUILDERS)
