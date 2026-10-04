from collections.abc import Callable
from typing import TypeAlias

from agent_dev_kit.agent_definition import AgentDefinition
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
from agent_dev_kit.project_config import (
    ProjectAgentDevKitConfig,
    apply_contextual_config,
)
from agent_dev_kit.providers.provider_base import AgentHandle, AgentProvider


AgentDefinitionBuilder: TypeAlias = Callable[..., AgentDefinition]


AGENT_BUILDERS: dict[str, AgentDefinitionBuilder] = {
    "product": build_product_definition,
    "pmo": build_pmo_definition,
    "architecture": build_architecture_definition,
    "ux_ui": build_ux_ui_definition,
    "backend": build_backend_definition,
    "frontend": build_frontend_definition,
    "database": build_database_definition,
    "security": build_security_definition,
    "testing": build_testing_definition,
    "reviewer": build_reviewer_definition,
    "documentation": build_documentation_definition,
    "triage": build_triage_definition,
    "devops": build_devops_definition,
    "performance": build_performance_definition,
    "observability": build_observability_definition,
    "data": build_data_definition,
}

AVAILABLE_AGENT_KEYS: tuple[str, ...] = tuple(AGENT_BUILDERS)


def normalize_agent_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def validate_enabled_agents(config: ProjectAgentDevKitConfig) -> None:
    unknown = sorted(
        {
            normalize_agent_key(key)
            for key in config.enabled_agents
            if normalize_agent_key(key) not in AGENT_BUILDERS
        }
    )
    if unknown:
        raise ValueError(
            "Unknown enabled agent(s): "
            + ", ".join(unknown)
            + ". Available: "
            + ", ".join(AVAILABLE_AGENT_KEYS)
        )


def is_agent_enabled(config: ProjectAgentDevKitConfig, key: str) -> bool:
    normalized = normalize_agent_key(key)
    return normalized in {
        normalize_agent_key(item) for item in config.enabled_agents
    }


def build_enabled_definitions(
    config: ProjectAgentDevKitConfig,
) -> dict[str, AgentDefinition]:
    """Build only definitions explicitly enabled by the consuming project."""

    validate_enabled_agents(config)

    resolved: dict[str, AgentDefinition] = {}
    for raw_key in config.enabled_agents:
        key = normalize_agent_key(raw_key)
        builder = AGENT_BUILDERS[key]
        definition = builder(model=config.provider.default_model)
        resolved[key] = apply_contextual_config(
            definition,
            config.agent(key),
        )

    return resolved


def create_enabled_agents(
    provider: AgentProvider,
    config: ProjectAgentDevKitConfig,
) -> dict[str, AgentHandle]:
    """Instantiate only enabled agents.

    Triage, when enabled, is created last and receives handoffs only to the
    other enabled agents. Disabled agents are neither instantiated nor exposed
    to Triage.
    """

    definitions = build_enabled_definitions(config)
    handles: dict[str, AgentHandle] = {}

    for key, definition in definitions.items():
        if key == "triage":
            continue
        handles[key] = provider.create_agent(definition)

    if "triage" in definitions:
        handles["triage"] = provider.create_agent(
            definitions["triage"],
            handoffs=tuple(handles.values()),
        )

    return handles
