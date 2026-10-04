# Contexto efectivo del proyecto consumidor

## Principio

La responsabilidad de un agente es reutilizable, pero sus decisiones técnicas dependen del proyecto donde está trabajando.

Ejemplo:

```text
Agent Backend
  + LibreriaIngles: Python / FastAPI
  = Backend especializado en ese stack

Agent Backend
  + OtroProyecto: Java / Spring Boot
  = el mismo rol aplicado a otro stack
```

## Qué se inyecta

Antes de crear un agente habilitado, Agent Dev Kit incorpora a sus instrucciones:

- nombre del proyecto consumidor;
- stack declarado en `.agent-dev-kit/project.yaml`;
- `extra_instructions` del agente;
- `project_rules` del agente.

## Qué NO se inyecta

Las opciones internas del proveedor no se incorporan al prompt/contexto.

Esto evita que una configuración como una API key, token, endpoint privado u otro secreto termine accidentalmente dentro de las instrucciones enviadas al modelo.

Los secretos deben gestionarse por mecanismos de entorno/configuración propios de cada proveedor.

## Ejemplo

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
```

Agent Backend y Agent Database pueden conocer este contexto sin cambiar sus responsabilidades nativas.
