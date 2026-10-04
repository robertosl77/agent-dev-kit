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

El modelo permite que varios nodos queden listos al mismo tiempo; la paralelización real puede incorporarse posteriormente sin cambiar el contrato del DAG.

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

## Documentación

Para trabajo durable, el plan debe incluir Agent Documentation cuando esté habilitado.

La documentación de ejecución puede vivir en la Issue asociada:

- pedido;
- plan;
- agentes que intervinieron;
- decisiones;
- tests;
- revisión;
- evidencia final.

Las decisiones que deben sobrevivir a la Issue también se escriben en artefactos durables del repositorio: código, configuración, tests o `docs/`.

## QA humano

El DAG termina técnicamente en Documentation/Reviewer según el caso.

La aceptación funcional final sigue siendo humana.
