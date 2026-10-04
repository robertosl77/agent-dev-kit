# Coordinación multi-especialista

## Dos grafos, dos responsabilidades

Agent Dev Kit utiliza dos conceptos diferentes.

### Grafo permanente de capacidades

Describe qué handoffs tienen sentido entre roles.

Ejemplos:

```text
Architecture → Backend
Architecture → Database
UX/UI → Frontend
Backend → Testing
Frontend → Testing
Testing → Reviewer
Reviewer → Documentation
```

Triage puede dirigir hacia todos los especialistas habilitados, pero no es necesario volver a Triage cuando el siguiente especialista es una continuación natural.

El grafo efectivo se filtra por `agents.enabled`.

Un agente deshabilitado nunca aparece como destino.

### DAG de ejecución por tarea

Una solicitud compuesta produce un plan específico con nodos y dependencias.

Ejemplo:

```text
                Architecture
                /           \
               ↓             ↓
          Database          UX/UI
              ↓               ↓
           Backend         Frontend
              \               /
               \             /
                 → Testing
                     ↓
                  Reviewer
                     ↓
               Documentation
                     ↓
                  QA humano
```

El DAG representa:

- qué trabajo existe;
- qué agente es dueño de cada nodo;
- qué nodos dependen de otros;
- qué resultados deben pasar a los siguientes;
- qué quedó completado o bloqueado.

## Ejecución inicial

La versión inicial ejecuta los nodos listos de manera secuencial.

El modelo permite ramas independientes y conserva sus dependencias, de modo que una paralelización futura no requiere cambiar el contrato del DAG.

Cada nodo recibe un resumen compacto del pedido, su objetivo/fase y los outputs de dependencias directas; no se reenvía por defecto todo el pedido conversacional.

## Agentes deshabilitados

Si una tarea necesita una responsabilidad cuyo agente no está habilitado:

```text
tarea
  ↓
requiere UX/UI
  ↓
UX/UI deshabilitado
  ↓
BLOCKED
```

No se permite:

- que Triage ocupe el lugar;
- que Frontend improvise UX;
- que un agente comodín absorba la responsabilidad.

## Activación por gates

El DAG no incorpora especialistas por rutina. Triage propone gates, razones, fases y dependencias; una política determinística valida que cada especialista tenga una justificación y que no falte un rol exigido por un riesgo activo.

Un mismo especialista puede participar en más de una fase sólo cuando las fases son distintas y necesarias. Repetir el mismo especialista en la misma fase se considera inválido.

## Documentación

Documentation sólo entra cuando existe conocimiento durable o un artefacto explícitamente solicitado. No se ejecuta después de cada subtarea.

- Product es dueño del contenido funcional;
- Architecture y especialistas técnicos son dueños del contenido técnico;
- Documentation consolida, formatea y mantiene sincronizados los artefactos.

El proyecto consumidor puede configurar plantillas para especificaciones funcionales/técnicas, ADRs y runbooks.

Ver `docs/orquestador_gates_trazas.md` para gates, fases, contexto mínimo y trazas.

## QA humano

El DAG termina técnicamente en Documentation/Reviewer según el caso.

La aceptación funcional final sigue siendo humana.
