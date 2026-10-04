# Orquestador — gates, fases, contexto y trazabilidad

## Objetivo

El orquestador debe resolver cada solicitud con el **subgrafo mínimo suficiente**
de especialistas.

No busca minimizar llamadas a cualquier precio. Busca evitar especialistas,
handoffs y contexto que no aporten valor, sin omitir responsabilidades
necesarias por riesgo o alcance.

## Arquitectura híbrida

La selección combina dos capas:

1. **Triage interpreta la solicitud** y propone señales estructuradas:
   clasificación, gates, especialistas, razones, fases y dependencias.
2. **La política determinística valida el plan** antes de ejecutar.

El modelo entiende semántica; el código impide inconsistencias estructurales.

## Gates

Cada gate representa una razón observable para activar una responsabilidad:

| Gate | Agente |
| --- | --- |
| product_definition | Product |
| delivery_planning | PMO |
| architecture_change | Architecture |
| ux_change | UX/UI |
| backend_change | Backend |
| frontend_change | Frontend |
| database_change | Database |
| security_risk | Security |
| testing_required | Testing |
| review_required | Reviewer |
| durable_documentation | Documentation |
| devops_change | DevOps |
| performance_concern | Performance |
| reliability_or_incident | Observability |
| data_change | Data |

Un especialista no puede aparecer en el DAG de policy v1 sin un gate activo o
sin una solicitud explícita del usuario mediante `forced_agents`.

## No activar por costumbre

```text
Cambiar un texto en una pantalla
→ Frontend
```

No implica automáticamente Product, Architecture, Security, Testing,
Reviewer o Documentation.

```text
Agregar recuperación de contraseña
→ Product / Security / Backend / Frontend / Testing / Reviewer
```

La segunda tarea tiene superficie funcional, de seguridad y regresión que
justifica un subgrafo mayor.

## Fases temporales

Un mismo especialista puede intervenir más de una vez únicamente si existen
fases diferentes y justificadas.

```text
Performance — analysis
      ↓
Backend — implementation
      ↓
Testing — verification
      ↓
Performance — verification
```

No se permiten dos nodos idénticos del mismo especialista en la misma fase.

## Contexto mínimo

Después del planning, cada nodo recibe:

- `request_summary`;
- su objetivo;
- su fase;
- outputs de dependencias directas;
- configuración contextual del agente;
- plantillas documentales sólo cuando corresponda.

No recibe automáticamente el pedido conversacional completo.

## Documentation y artefactos

Documentation no participa por cada subtarea.

Los artefactos durables se declaran explícitamente en el plan.
Si existen artefactos, Documentation es obligatorio.

### Dueños de contenido

- especificación funcional → Product;
- especificación técnica → Architecture + especialistas técnicos;
- ADR → Architecture;
- runbook → DevOps/Observability;
- Documentation → consolidación, formato, sincronización y trazabilidad.

### Plantillas del consumidor

```yaml
documentation:
  templates:
    functional_spec: docs/templates/functional-spec.md
    technical_spec: docs/templates/technical-spec.md
    adr: docs/templates/adr.md
    runbook: docs/templates/runbook.md
```

La plantilla sólo se carga en el contexto del nodo Documentation que necesita
ese artefacto.

El usuario puede pedir explícitamente crear/actualizar un documento aunque el
gate automático no lo hubiera elegido.

## Trazas estructuradas

Los planes policy v1 producen una traza auditable con:

- resumen del pedido;
- fingerprint SHA-256 del pedido normalizado;
- clasificación;
- Issue asociada cuando exista;
- gates;
- agentes seleccionados;
- agentes considerados pero omitidos y motivo;
- DAG y fases;
- llamadas a provider;
- duración;
- tamaño de contexto;
- tokens cuando el provider los expone;
- revisitas;
- overrides humanos;
- estado técnico y QA.

No se almacena chain-of-thought.
El pedido original tampoco se conserva por defecto.

## Persistencia local opcional

```yaml
orchestration:
  trace:
    path: .agent-dev-kit/runtime/orchestration.jsonl
    retain_request_text: false
    propose_issues: true
```

El path de trace debe permanecer dentro del root del proyecto.
`.agent-dev-kit/runtime/` debe mantenerse fuera de Git cuando contiene
telemetría cruda.

## Mejora continua supervisada

Las trazas no modifican automáticamente Agent Dev Kit.

```text
trazas reales
   ↓
revisión periódica
   ↓
hallazgo objetivo
   ↓
Issue de mejora
   ↓
cambio de gate/policy
   ↓
test de regresión
   ↓
nueva versión
```

El framework puede producir una `IssueProposal` a partir de señales repetidas
como loops/revisitas o tareas bloqueadas. Crear la Issue real requiere una
integración GitHub autorizada y una política que lo permita.

Crear la Issue nunca autoriza al sistema a auto-modificar código o políticas.

## Métricas de eficiencia

- cantidad de nodos;
- llamadas a providers;
- contexto enviado;
- tokens cuando estén disponibles;
- duración;
- revisitas;
- especialistas omitidos/seleccionados.

Reducir esas métricas nunca justifica eliminar un especialista requerido.

## QA humano

El DAG puede terminar técnicamente en Testing, Security, Reviewer o
Documentation según la tarea.

La aceptación funcional final continúa siendo humana.
