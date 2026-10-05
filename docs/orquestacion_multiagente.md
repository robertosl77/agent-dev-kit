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

## Planner aislado y salida estructurada

La planificación no reutiliza el Triage conversacional. El runtime crea una
instancia separada, `Agent Triage Planner`, sin handoffs ni herramientas. De
esta forma el grafo permanente de capacidades no puede interferir con la fase
que construye el DAG.

Cuando el provider soporta structured output, el planner usa
`StructuredTaskPlan` como contrato tipado. OpenAI lo expone mediante
`output_type`, por lo que la salida se valida en el provider antes de llegar al
orquestador.

Para providers sin soporte nativo se mantiene un fallback textual controlado:

1. la salida se parsea con el mismo schema estricto;
2. si falla, se permite exactamente un intento de reparación;
3. si vuelve a fallar, la planificación termina con error;
4. cualquier handoff inesperado durante planning se rechaza sin reparación.

El contrato estricto exige todos los campos del plan y rechaza campos
desconocidos, tipos incorrectos y valores fuera de los enums del orquestador.

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
