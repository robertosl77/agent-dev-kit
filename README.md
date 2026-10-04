# agent-dev-kit

Framework reutilizable de agentes especializados para acompañar el desarrollo de aplicaciones.

## Estado

El framework tiene un catálogo base de 16 agentes, configuración contextual por proyecto, selección de agentes habilitados, runtime persistente, abstracción de proveedor y capa neutral de herramientas.

Todavía no tiene una versión estable publicada. El versionado inicial se realizará cuando la estructura base quede validada.

## Principios

- Los agentes representan **responsabilidades**, no tecnologías.
- El proyecto consumidor define stack, reglas locales, agentes habilitados y proveedor.
- Los agentes no habilitados no se instancian ni reciben handoffs.
- Triage enruta; no debe intervenir en cada turno si ya existe un especialista activo.
- El framework no queda acoplado a OpenAI: el proveedor concreto vive detrás de un adaptador.
- Las decisiones duraderas deben quedar en código, configuración, tests o documentación del proyecto.

## Catálogo base

```text
Agent Product
Agent PMO
Agent Architecture
Agent UX/UI
Agent Backend
Agent Frontend
Agent Database
Agent Security
Agent Testing
Agent Reviewer
Agent Documentation
Agent Triage
Agent DevOps
Agent Performance
Agent Observability
Agent Data
```

## Estructura principal

```text
agent-dev-kit/
├── docs/
│   ├── agentes/
│   │   ├── agent_product.md
│   │   ├── agent_pmo.md
│   │   ├── agent_architecture.md
│   │   ├── agent_ux_ui.md
│   │   ├── agent_backend.md
│   │   ├── agent_frontend.md
│   │   ├── agent_database.md
│   │   ├── agent_security.md
│   │   ├── agent_testing.md
│   │   ├── agent_reviewer.md
│   │   ├── agent_documentation.md
│   │   ├── agent_triage.md
│   │   ├── agent_devops.md
│   │   ├── agent_performance.md
│   │   ├── agent_observability.md
│   │   └── agent_data.md
│   ├── activacion_agentes.md
│   ├── catalogo_agentes.md
│   ├── configuracion_nativa_y_contextual.md
│   ├── contexto_proyecto.md
│   ├── herramientas_agentes.md
│   └── proveedores.md
├── examples/
│   └── libreria_ingles/
│       └── .agent-dev-kit/
├── src/
│   └── agent_dev_kit/
│       ├── agents/
│       │   └── agent_*.py
│       ├── providers/
│       │   ├── provider_base.py
│       │   └── provider_openai.py
│       ├── agent_catalog.py
│       ├── agent_definition.py
│       ├── project_config.py
│       ├── provider_config.py
│       ├── provider_registry.py
│       ├── runtime.py
│       └── tooling.py
├── tests/
└── pyproject.toml
```

## Configuración del proyecto consumidor

Agent Dev Kit no se copia dentro del proyecto consumidor.

El consumidor mantiene su propia configuración:

```text
MiProyecto/
└── .agent-dev-kit/
    ├── project.yaml
    └── agents/
        ├── pmo.yaml
        ├── architecture.yaml
        └── ...
```

Ejemplo:

```yaml
project:
  name: LibreriaIngles

stack:
  backend:
    language: Python
    framework: FastAPI
  frontend:
    framework: Angular
  ui:
    framework: Bootstrap
  database:
    engine: SQLite

provider:
  name: openai

agents:
  enabled:
    - pmo
    - architecture
    - backend
    - frontend
    - testing
    - triage
```

## Documentación

- [Catálogo de agentes](docs/catalogo_agentes.md)
- [Configuración nativa y contextual](docs/configuracion_nativa_y_contextual.md)
- [Activación de agentes](docs/activacion_agentes.md)
- [Contexto del proyecto](docs/contexto_proyecto.md)
- [Herramientas por agente](docs/herramientas_agentes.md)
- [Coordinación multi-especialista](docs/orquestacion_multiagente.md)
- [Preferencias persistentes del usuario](docs/preferencias_usuario.md)
- [Ejecución, proveedores y fallback](docs/ejecucion_y_fallback.md)
- [Smoke test pre-versionado](docs/smoke_test.md)
- [Interfaz MCP para clientes de chat](docs/interfaz_mcp.md)
- [Proveedores](docs/proveedores.md)
- [Documentación individual de agentes](docs/agentes/)

## Proveedor

La primera implementación concreta es OpenAI Agents SDK, aislada detrás de `OpenAIProvider`.

Otros proveedores pueden agregarse sin reescribir los agentes del catálogo.

## Desarrollo

Instalación para desarrollo:

```bash
pip install -e ".[dev]"
```

Proveedor OpenAI opcional:

```bash
pip install -e ".[openai]"
```

Tests:

```bash
pytest
```

Las modernizaciones del framework se gestionan mediante GitHub Issues con códigos `M-xxx`.


## Ejecución

Conversación interactiva:

```bash
agent-dev-kit run .
```

Tarea multi-especialista:

```bash
agent-dev-kit task . "descripción de la tarea"
```


## MCP

Exponer el proyecto a un host MCP local:

```bash
agent-dev-kit mcp .
```

Streamable HTTP local:

```bash
agent-dev-kit mcp . --transport streamable-http
```

El servidor queda vinculado al proyecto indicado al arrancar y no acepta
rutas de repositorio desde las herramientas.
