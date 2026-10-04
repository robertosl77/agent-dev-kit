# agent-dev-kit

Framework reutilizable de agentes especializados para acompañar el desarrollo de aplicaciones.

## Estado

El proyecto está en etapa inicial de definición e implementación de su arquitectura base.

## Documentación

- [Catálogo de agentes](docs/catalogo_agentes.md): responsabilidad, alcance, límites, entregables, herramientas y handoffs.
- [Proveedores](docs/proveedores.md): capa abstracta que desacopla los agentes de OpenAI, Copilot, Claude u otros motores.
- Las modernizaciones se gestionan mediante GitHub Issues con códigos `M-xxx`.

## Principio central

Los agentes representan **responsabilidades** (Product, Architecture, Backend, Database, UX/UI, etc.).

La tecnología concreta y el proveedor pertenecen al proyecto consumidor:

```text
Proyecto A
  Agent Backend → Python / FastAPI
  Provider      → OpenAI

Proyecto B
  Agent Backend → Java / Spring Boot
  Provider      → otro adaptador
```

## Estructura actual

```text
agent-dev-kit/
├── docs/
│   ├── catalogo_agentes.md
│   └── proveedores.md
├── src/
│   └── agent_dev_kit/
│       ├── agent_definition.py
│       ├── agents/
│       │   └── agent_pmo.py
│       ├── provider_config.py
│       ├── provider_registry.py
│       └── providers/
│           ├── provider_base.py
│           └── provider_openai.py
├── tests/
└── pyproject.toml
```

Los archivos `agent_*.py` se incorporan a medida que se implementan los agentes del catálogo. El primero disponible es `Agent PMO`.
