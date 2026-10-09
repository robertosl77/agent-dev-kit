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

El prompt de planificación incluye el mapa completo `risk_flag -> agente
requerido` (misma fuente que el validador, `RISK_REQUIRED_AGENTS`), para que el
modelo no tenga que adivinarlo. Si el plan declara un flag sin seleccionar a su
agente, el único intento de reparación explica las dos salidas válidas: quitar
el flag o seleccionar el agente y agregarle un nodo (M-083).

Cada salida rechazada del planner (plan y reparación) se agrega a
`.agent-dev-kit/runtime/planner-rejections.jsonl` con fecha, etapa, error,
fingerprint del pedido y la salida recortada. El error final muestra esa ruta.

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

## Budgets duros y reutilización

Cada proyecto puede fijar límites duros para una ejecución:

```yaml
orchestration:
  budgets:
    max_dag_nodes: 12
    max_provider_calls: 24
    max_revisits: 2
    max_context_chars: 16000
    max_dependency_evidence_chars: 8000
```

Los límites se validan antes de consumir la siguiente llamada. Si continuar
excedería el presupuesto, la tarea pasa a `requires_human_approval` y el
Gateway devuelve el budget afectado, límite, valor observado y etapa.

`max_provider_calls` incluye planning, reparación del planner y ejecución de
nodos. Hasta M-036, `model_calls` conserva compatibilidad y refleja el mismo
contador; M-036 separará provider runs de requests reales al modelo.

La reutilización es exclusivamente intra-task. Si dos nodos tienen el mismo
input efectivo —mismo agente, fase, objetivo y evidencia de dependencias— el
segundo reutiliza el output/evidence ya obtenido y no vuelve a llamar al
provider. No existe cache automática entre tareas.

Antes de enviar contexto a un nodo, la evidencia duplicada se consolida y el
exceso se recorta localmente con una marca explícita. Estas operaciones, junto
con gates, policies y validaciones de budgets, son determinísticas y no consumen
una llamada adicional al modelo.

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
- provider calls / llamadas compatibles a modelo;
- llamadas evitadas por reutilización;
- contexto enviado, deduplicaciones y recortes;
- eventos de budget;
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
    max_entries: 1000
```

La telemetría runtime se excluye del versionado Git.


El path de trazas se resuelve contra el `project_root` y se rechaza si intenta
escapar mediante una ruta absoluta, `../` o un symlink que resuelva fuera del
proyecto. El store mantiene un lock compartido por path para escrituras
concurrentes dentro del proceso, aplica retención por cantidad máxima de
entradas y ofrece `iter_read()` para consumo incremental.

Las trazas se persisten también en estados no exitosos relevantes:
`interrupted`, `blocked`, `failed` y `requires_human_approval`. Si una
ejecución interrumpida se reanuda y termina correctamente, queda un evento
posterior `completed`, preservando ambos hechos.

`request_summary` se normaliza a una línea, se limita en longitud y redacta
patrones obvios de secretos. El pedido completo sigue sin persistirse por
defecto.

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
