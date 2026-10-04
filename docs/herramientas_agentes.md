# Herramientas por agente

## Objetivo

Agent Dev Kit debe poder asignar herramientas a cada especialista sin acoplar el framework a OpenAI, Copilot u otro proveedor.

## Regla

Las herramientas concretas las registra el proyecto consumidor en runtime.

Ejemplo conceptual:

```text
PMO
  ├── github_issues
  └── github_pull_requests

Testing
  ├── test_runner
  └── coverage

Reviewer
  ├── git_diff
  └── ci_status
```

## Configuración contextual

Un agente puede declarar las herramientas que necesita:

```yaml
agent: pmo

tools:
  - github_issues
  - github_pull_requests
```

Declarar una herramienta no la crea.

El proyecto consumidor debe registrarla para el proveedor activo mediante `ToolRegistry`.

## Seguridad

Una herramienta:

- solo se entrega al agente que la solicita;
- debe pertenecer al mismo proveedor activo;
- debe estar registrada explícitamente;
- si falta, la creación falla de forma visible.

Esto evita que un agente obtenga accidentalmente capacidades que el proyecto no decidió concederle.

## Integraciones concretas

Esta capa define el contrato.

GitHub, Docker, CI/CD, navegador, base de datos u otras herramientas concretas pueden implementarse después por el consumidor o por módulos específicos.
