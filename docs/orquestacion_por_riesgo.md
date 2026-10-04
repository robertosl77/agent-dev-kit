# Orquestación por riesgo y subgrafo mínimo

## Objetivo

El orquestador debe resolver cada solicitud con el subgrafo mínimo suficiente de
especialistas. Un agente no participa por estar habilitado: participa porque una
responsabilidad, un riesgo, una dependencia o un artefacto lo exige.

## Flujo

```text
pedido
  ↓
preclasificación determinística de riesgos críticos
  ↓
Triage clasifica y propone
  ↓
perfil de riesgo / impacto / artefactos
  ↓
decisión explícita por cada especialista habilitado
  ↓
validación determinística de contratos, riesgos y policies
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
determinísticamente al especialista correspondiente. Esa declaración ya no es la
única fuente de verdad: antes de ejecutar, el framework vuelve a clasificar de
forma determinística riesgos críticos como autenticación, cambios de esquema,
APIs públicas, datos sensibles y deployment. Los riesgos detectados se fusionan
con los de Triage y no pueden ser omitidos para evitar un gate.

`risk_flags`, fases y artefactos durables usan contratos cerrados. Un valor
desconocido o un typo se rechaza; no se degrada silenciosamente a texto libre.

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

## Policies determinísticas del proyecto

El proyecto consumidor puede endurecer el routing desde
`.agent-dev-kit/project.yaml` con reglas estructuradas:

```yaml
orchestration:
  policies:
    - id: auth_requires_review
      when:
        any_risk_flags:
          - auth_change
      require_agents:
        - reviewer
```

Las policies sólo agregan requisitos. No pueden desactivar invariantes nativas
del framework. El schema valida IDs, riesgos y agentes al cargar la
configuración. Si una policy activada contradice la propuesta de Triage, el plan
se rechaza antes de ejecutar. La traza registra los IDs de las policies
activadas y los riesgos detectados por la preclasificación independiente.

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
- riesgos finales y riesgos detectados independientemente;
- artefactos;
- policies de proyecto activadas;
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
