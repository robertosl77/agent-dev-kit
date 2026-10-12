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
- `project_rules` del agente;
- la política `git_workflow`, presentada como lo que el framework aplica en
  código (configuración declarada, subconjunto de las reglas del proyecto; no
  es estado verificado de GitHub);
- `context.rule_sources`: los documentos del repo que mandan en cada tema
  (M-085). Cuando una tarea depende de esas reglas, el agente las lee y las
  sigue por encima del resumen de `git_workflow`.

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
