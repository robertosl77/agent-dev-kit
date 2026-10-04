# Catálogo de agentes — Agent Dev Kit

## Propósito

Este documento define **qué responsabilidad tiene cada agente, hasta dónde llega y qué debe entregar**.

No define todavía prompts, modelos, proveedores ni implementación interna. Es el contrato conceptual del framework.

## Principios

1. **Responsabilidad antes que tecnología.** Un agente representa un rol (Backend, Database, UX/UI), no una tecnología concreta.
2. **La tecnología la define el proyecto consumidor.** Por ejemplo, Agent Backend puede trabajar con Python/FastAPI o Java/Spring Boot.
3. **Los límites importan.** Un agente no debe absorber responsabilidades de otro solo porque puede resolverlas técnicamente.
4. **Las decisiones duraderas viven en el proyecto.** Componentes, reglas, arquitectura, tests y documentación no deben depender solo de memoria conversacional.
5. **QA funcional final sigue siendo humano.** Agent Testing y Agent Reviewer preparan y revisan; no reemplazan la aceptación del responsable del producto.
6. **Los handoffs deben ser explícitos.** Si una necesidad sale del alcance de un agente, deriva al especialista correspondiente.

## Catálogo base

| Agente / archivo | Responsabilidad | Alcance | Resultado / entregable principal | Herramientas típicas |
|---|---|---|---|---|
| `agent_product.py` | Convertir una idea, necesidad o problema de negocio en una definición construible. | Discovery/business analysis, visión, stakeholders, alcance, casos de uso, requisitos funcionales/no funcionales y restricciones de accesibilidad, privacidad/compliance, security, reliability u operabilidad cuando correspondan. | Definición funcional / PRD y roadmap conceptual de capacidades. | Documentación del proyecto, conversaciones de discovery, requisitos, decisiones de negocio, Issues como fuente de contexto. |
| `agent_pmo.py` | Gobernar y ordenar el trabajo una vez definido qué producto se quiere construir. | Backlog, prioridades, dependencias, bloqueos, secuencia recomendada, estado, iteraciones, seguimiento y dinámica tipo Scrum. | Backlog gobernado y plan de ejecución priorizado. | GitHub Issues, Projects, PRs, ramas, commits, milestones y dependencias. |
| `agent_architecture.py` | Definir y proteger la estructura técnica global del sistema. | Capas, módulos, componentes, límites de responsabilidad, integraciones, patrones, decisiones transversales y prevención de duplicación arquitectónica. | Diseño arquitectónico, decisiones y advertencias de impacto transversal. | Código del repositorio, diagramas, documentación técnica, dependencias, ADRs y contratos entre módulos. |
| `agent_ux_ui.py` | Diseñar y mantener una experiencia e interfaz coherentes. | Flujos, usabilidad, accesibilidad, responsive, sistema de diseño, componentes reutilizables y consistencia visual. | Especificación UX/UI y evolución del sistema de diseño del proyecto consumidor. | Frontend, design tokens, componentes, CSS/SCSS, framework UI, screenshots/prototipos y reglas visuales del proyecto. |
| `agent_backend.py` | Implementar lógica de servidor y servicios de aplicación. | APIs, servicios, reglas de negocio, integraciones, validaciones y acceso a persistencia desde la aplicación. | Implementación backend y contratos de servicio/API. | Código backend, framework configurado, OpenAPI, tests, logs y herramientas del stack. |
| `agent_frontend.py` | Implementar la aplicación cliente. | Componentes, navegación, estado, formularios, integración con APIs y comportamiento de navegador. | Implementación frontend alineada con UX/UI y contratos backend. | Código frontend, framework configurado, build, tests, navegador y sistema de diseño. |
| `agent_database.py` | Diseñar y mantener la persistencia operativa. | Modelo de datos, SQL, índices, constraints, migraciones, vistas, triggers, funciones/procedimientos y rendimiento de consultas. | Esquema/migraciones y lógica de base de datos segura y mantenible. | Motor configurado (SQLite, PostgreSQL, Oracle, etc.), SQL, migraciones, explain plans y herramientas DBA. |
| `agent_security.py` | Gobernar riesgo técnico de seguridad y privacy assurance. | Autenticación, autorización, secretos, exposición de datos, threat modeling, security testing, privacy engineering, compliance técnico, supply chain y hardening. | Riesgos identificados y controles de seguridad implementables/verificados. | Código, configuración, dependencias, secretos/config, auditorías, threat modeling y CI. |
| `agent_testing.py` | Automatizar validaciones técnicas repetibles. | Unit/integration/regression, caja blanca, security regression, accessibility checks automatizables, fixtures, edge cases y cobertura. | Suite automatizada y evidencia técnica de validación. | Frameworks de test, CI, cobertura, fixtures, mocks, generadores de datos y código fuente. |
| `agent_reviewer.py` | Revisar técnicamente una entrega antes de presentarla a QA humano. | Comparar lo pedido con lo implementado, buscar bugs, regresiones, deuda, inconsistencias, tests faltantes, impacto lateral y documentación faltante. | Informe de revisión técnica y correcciones/recomendaciones previas a entrega. | Issue original, diff/PR, commits, tests, CI, documentación y código afectado. |
| `agent_documentation.py` | Mantener sincronizado el conocimiento del proyecto con su implementación. | Documentación funcional/técnica, instalación, arquitectura, decisiones, runbooks y actualización por cambios relevantes. | Documentación actualizada, consistente y trazable. | Código, Issues, PRs, ADRs, README, docs y diagramas. |
| `agent_triage.py` | Identificar quién debe intervenir y transferir el contexto. | Clasificación de solicitudes, support/incident intake, selección de especialista, handoff y re-enrutamiento cuando cambia el dominio. | Trabajo correctamente asignado al especialista adecuado. | Catálogo de agentes, contexto del proyecto, metadatos de tareas y estado de conversación. |
| `agent_devops.py` | Hacer que la aplicación sea reproducible, desplegable y operable. | Docker, CI/CD, ambientes, platform engineering, developer self-service, release operations, rollout/rollback, infraestructura y security checks de pipeline. | Pipeline y entorno reproducible de build/deploy/operación. | Docker, CI/CD, hosting/cloud, variables de entorno, scripts e infraestructura como código cuando corresponda. |
| `agent_performance.py` | Mejorar rendimiento y eficiencia de recursos/costos. | Latencia, CPU/memoria, consultas lentas, caché, batching, llamadas innecesarias, tokens y elección entre lógica determinística e IA. | Diagnóstico y propuesta de optimización con métricas antes/después. | Profilers, métricas, logs, traces, explain plans, medición de tokens/costo y benchmarks. |
| `agent_observability.py` | Hacer visible y medible el comportamiento/reliability de una aplicación. | Logs, métricas, trazas, SLIs/SLOs, alertas, dashboards, incident management, diagnóstico y post-incident learning. | Esquema de observabilidad que permita detectar y explicar incidentes. | Logging, métricas, tracing, dashboards, alertas y herramientas de monitoreo del entorno. |
| `agent_data.py` | Preparar y explotar datos para analítica, reporting o intercambio entre sistemas. | ETL/ELT, calidad de datos, pipelines, datasets analíticos, reporting y data warehouse/lake cuando aplique. | Pipeline/dataset analítico reproducible y validado. | SQL, APIs/fuentes, herramientas ETL, notebooks/scripts, almacenamiento analítico y BI. |

## Límites y handoffs principales

### Agent Product vs Agent PMO

**Agent Product** responde principalmente:

> ¿Qué producto necesitamos construir y qué capacidades debe tener?

Puede producir un roadmap **conceptual de producto**.

**Agent PMO** responde principalmente:

> ¿Cómo organizamos, priorizamos y seguimos el trabajo necesario para construirlo?

Convierte la definición del producto en backlog ejecutable, dependencias, prioridades e iteraciones.

### Agent Architecture vs agentes de implementación

Architecture no debe programar una feature completa por comodidad. Su función es definir o revisar la estructura y luego derivar la implementación.

Ejemplo de referencia:

- Beneficio = qué recibe una persona.
- Invitación/Campaña = cómo llega una persona a ese beneficio.

Si dos mecanismos empiezan a duplicar la lógica de otorgamiento, Agent Architecture debe detectar la duplicación y proponer una capa común antes de seguir implementando.

### Agent UX/UI vs proyecto consumidor

Agent UX/UI conoce **cómo diseñar y mantener un sistema de diseño**.

Los componentes concretos viven en el proyecto consumidor:

```text
Agent Dev Kit
  └── conoce la responsabilidad UX/UI

Librería Inglés
  ├── Bootstrap
  ├── tokens visuales
  ├── botón activar/desactivar
  ├── collapse
  ├── cards
  └── reglas propias
```

Otro proyecto puede usar React/Tailwind y tendrá componentes diferentes.

### Agent Database vs Agent Data

**Database** trabaja sobre la persistencia operativa de la aplicación.

Ejemplos:
- tabla;
- constraint;
- índice;
- query;
- migración;
- trigger;
- función/procedimiento.

**Data** mueve y transforma información para análisis o intercambio.

Ejemplo:
- extraer progreso de empleados;
- transformar actividad en métricas mensuales;
- validar calidad;
- cargar dataset analítico;
- alimentar dashboard empresarial.

### Agent Testing vs QA humano

Agent Testing automatiza lo repetible y puede hacer caja blanca.

El QA humano conserva:
- validación funcional;
- caja negra;
- aceptación de producto;
- criterio sobre si el resultado realmente cumple lo pedido.

### Agent Reviewer

Se ejecuta idealmente antes de entregar una rama o PR al responsable humano.

Debe revisar:

1. qué pedía la Issue;
2. qué cambió realmente;
3. si hay impacto lateral;
4. si faltan tests;
5. si falta documentación;
6. si la implementación contradice decisiones existentes;
7. si aparecen nuevas tareas o deuda que conviene registrar.

## Tecnología y responsabilidad son ejes distintos

Ejemplo:

```text
Proyecto A
Agent Backend
  → Python
  → FastAPI
  → SQLAlchemy

Proyecto B
Agent Backend
  → Java
  → Spring Boot
  → Hibernate
```

El agente sigue teniendo la misma responsabilidad. El proyecto consumidor define el stack que debe aplicar.

Lo mismo ocurre con Agent Database:

```text
Proyecto A → SQLite
Proyecto B → PostgreSQL
Proyecto C → Oracle
```

## Convención de archivos

Los agentes deben usar el prefijo `agent_` para quedar agrupados:

```text
agent_product.py
agent_pmo.py
agent_architecture.py
agent_ux_ui.py
agent_backend.py
agent_frontend.py
agent_database.py
agent_security.py
agent_testing.py
agent_reviewer.py
agent_documentation.py
agent_triage.py
agent_devops.py
agent_performance.py
agent_observability.py
agent_data.py
```

## Estado de implementación

Este documento define el **catálogo y los contratos conceptuales**.

Los agentes todavía no se consideran configurados ni implementados por el mero hecho de aparecer aquí. Su comportamiento, prompts, herramientas concretas, proveedor y runtime se implementarán en modernizaciones posteriores.


## Auditoría SDLC

El catálogo fue contrastado contra NIST SSDF/DevSecOps, OWASP SAMM, Microsoft
SDL, Google SRE, W3C ARRM y NIST Privacy Framework.

La conclusión para v0.1.0 es mantener los **16 agentes** y ampliar
responsabilidades cercanas en lugar de crear roles por organigrama.

Ver [Auditoría de cobertura de responsabilidades del SDLC](auditoria_roles_sdlc.md).
