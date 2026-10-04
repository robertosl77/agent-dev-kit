# agent-dev-kit

Framework reutilizable de agentes especializados para acompañar el desarrollo de aplicaciones.

## Estado

El proyecto está en etapa inicial de definición de responsabilidades y arquitectura.

## Documentación

- [Catálogo de agentes](docs/catalogo_agentes.md): responsabilidad, alcance, límites, entregables, herramientas y handoffs.
- Las modernizaciones se gestionan mediante GitHub Issues con códigos `M-xxx`.

## Principio central

Los agentes representan **responsabilidades** (Product, Architecture, Backend, Database, UX/UI, etc.).

La tecnología concreta pertenece al proyecto consumidor:

```text
Agent Backend
  ├── proyecto A → Python / FastAPI
  └── proyecto B → Java / Spring Boot
```

Los prompts, proveedores y comportamiento de ejecución se incorporarán en las siguientes modernizaciones.
