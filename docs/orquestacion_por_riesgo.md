# Orquestación por riesgo y subgrafo mínimo

## Objetivo

El orquestador debe resolver cada solicitud con el subgrafo mínimo suficiente de
especialistas. Un agente no participa por estar habilitado: participa porque una
responsabilidad, un riesgo, una dependencia o un artefacto lo exige.

## Flujo

```text
pedido
  ↓
Triage clasifica
  ↓
perfil de riesgo / impacto / artefactos
  ↓
decisión explícita por cada especialista habilitado
  ↓
validación determinística de gates
  ↓
DAG mínimo con fases y dependencias
  ↓
ejecución
  ↓
traza estructurada
  ↓
QA humano / PR
```

## Gates

Triage debe producir una decisión `selected=true/false` para cada especialista
habilitado, salvo Triage. Cada decisión incluye un gate y una razón breve.

Ejemplos:

- Security entra por superficie de seguridad real, no por rutina.
- Testing entra por cambio de comportamiento, regresión, lógica, contratos,
  integraciones, edge cases o controles definidos.
- Architecture entra por límites, impacto transversal, integraciones o diseño
  durable; no por un cambio local trivial.
- Documentation entra cuando existe conocimiento durable o pedido documental
  explícito; no después de cada subtarea.
- Performance, Observability, DevOps y Data sólo entran cuando su
  responsabilidad es material para la solicitud.

El planner declara además `risk_flags`. Algunos flags exigen
determinísticamente al especialista correspondiente. Si el plan contradice sus
propios riesgos, se rechaza antes de ejecutar.

## Fases

Cada nodo registra su fase. Ejemplos:

- `discovery`;
- `design`;
- `implementation`;
- `validation`;
- `documentation`;
- `release`.

Las dependencias determinan el orden real. Un mismo especialista puede aparecer
en más de una fase sólo cuando existe información nueva que justifica volver a
convocarlo.

## Documentación funcional y técnica

### Especificación funcional

Product es dueño del contenido funcional: objetivo, alcance, actores, reglas de
negocio, casos de uso y criterios de aceptación.

Documentation consolida y mantiene el artefacto cuando corresponde.

### Especificación técnica

Architecture y los especialistas técnicos son dueños de las decisiones técnicas
que les corresponden.

Documentation consolida y mantiene sincronizado el artefacto.

El proyecto consumidor puede configurar plantillas:

```yaml
orchestration:
  document_templates:
    functional_spec: .agent-dev-kit/templates/functional_spec.md
    technical_spec: .agent-dev-kit/templates/technical_spec.md
```

El usuario también puede pedir explícitamente crear o actualizar un documento,
lo que activa el gate correspondiente.

## Contexto mínimo por nodo

Triage recibe la solicitud original para planificar.

Los especialistas posteriores reciben por defecto:

- resumen factual de la tarea;
- fase;
- objetivo propio;
- outputs de sus dependencias.

No se reenvía automáticamente el prompt/conversación completa a cada nodo.

## Traza

Cada ejecución puede persistir una traza JSONL local configurable con:

- resumen de solicitud;
- fingerprint;
- clasificación;
- riesgos;
- artefactos;
- especialistas seleccionados y omitidos con razón;
- DAG/fases;
- llamadas a modelos;
- handoffs inesperados;
- revisitas;
- duración por nodo;
- estado.

Por defecto no se persiste el pedido completo.

```yaml
orchestration:
  trace:
    enabled: true
    path: .agent-dev-kit/runtime/orchestration-traces.jsonl
    persist_full_request: false
```

La telemetría runtime se excluye del versionado Git.

## Mejora continua

Las trazas no modifican automáticamente el framework.

Una revisión explícita puede detectar:

- rutas inconsistentes para solicitudes equivalentes;
- revisitas repetidas;
- especialistas innecesarios;
- especialistas omitidos;
- exceso de llamadas/contexto.

Los patrones detectables se convierten en candidatos de mejora. Cuando exista
una herramienta de Issues habilitada, una integración puede transformar el
candidato en una Issue para revisión humana.

La corrección se implementa por el workflow normal y debe agregar tests de
regresión del orquestador.

## Regla de seguridad

Nunca persistir chain-of-thought, razonamiento privado, secretos ni prompts
completos por defecto. La traza contiene decisiones observables y evidencia
operativa suficiente para auditar el enrutamiento.
