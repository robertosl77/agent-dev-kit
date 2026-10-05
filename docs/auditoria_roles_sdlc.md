# Auditoría de cobertura de responsabilidades del SDLC

## Objetivo

Validar que el catálogo de Agent Dev Kit cubra las responsabilidades relevantes
del ciclo de vida de software sin copiar un organigrama ni crear un agente por
cada puesto existente en una empresa.

La unidad de diseño es la **responsabilidad**.

Una persona real puede cumplir varios roles y un agente puede absorber
responsabilidades cercanas siempre que:

- exista un dueño principal claro;
- no se mezclen responsabilidades contradictorias;
- el entregable siga siendo coherente;
- el orquestador pueda decidir cuándo activarlo;
- la concentración reduzca handoffs sin crear un agente comodín.

## Referencias contrastadas

La revisión se apoyó en:

- NIST Secure Software Development Framework (SSDF):
  https://csrc.nist.gov/projects/ssdf
- NIST NCCoE DevSecOps / análisis de roles SSDF:
  https://pages.nist.gov/nccoe-devsecops/appendix-c.html
- OWASP SAMM:
  https://owaspsamm.org/model/
- Microsoft Security Development Lifecycle:
  https://www.microsoft.com/en-us/securityengineering/sdl/practices
- Google SRE — Incident Management:
  https://sre.google/resources/practices-and-processes/incident-management-guide/
- Google SRE — The Art of SLOs:
  https://sre.google/resources/practices-and-processes/art-of-slos/
- W3C WAI Accessibility Roles and Responsibilities Mapping:
  https://www.w3.org/WAI/planning/arrm/
- NIST Privacy Framework:
  https://www.nist.gov/privacy-framework

Las fuentes se usan como referencia de responsabilidades, no como requisito de
copiar sus estructuras organizacionales.

## Conclusión

Para v0.1.0 no se justifica agregar nuevos agentes.

Los 16 agentes actuales pueden cubrir los gaps encontrados si se explicitan los
límites y handoffs siguientes.

## Mapa de responsabilidades

| Área | Dueño principal | Colaboradores | Decisión |
| --- | --- | --- | --- |
| Product discovery / business analysis | Product | PMO | ampliar Product |
| Requisitos funcionales y NFR | Product | Architecture, Security, UX/UI, Observability | ampliar Product |
| Backlog / coordinación / readiness | PMO | Product, Reviewer | ya cubierto + release follow-up |
| Arquitectura | Architecture | especialistas técnicos | ya cubierto |
| UX y accesibilidad | UX/UI | Frontend, Testing, QA humano | ampliar UX/UI y Testing |
| Backend | Backend | Database, Security, Testing | ya cubierto |
| Frontend | Frontend | UX/UI, Security, Testing | ya cubierto |
| Persistencia operacional | Database | Security | agregar lifecycle de datos requerido |
| Pipelines/analítica | Data | Database, Security | agregar privacidad/lifecycle requerido |
| Security assurance | Security | Testing, DevOps, Reviewer | reforzado por M-025 |
| Privacy / compliance técnico | Security | Product, Database, Data, Documentation | ampliar Security; no crear agente |
| Testing técnico | Testing | especialistas | ya cubierto + accesibilidad/security regression |
| Revisión técnica | Reviewer | Testing, Security, Architecture | ya cubierto |
| Reliability / SRE | Observability | DevOps, Performance, PMO | ampliar Observability |
| Incident management | Observability | Triage, DevOps, Security, PMO | ampliar Observability/Triage |
| Platform engineering | DevOps | Architecture | ampliar DevOps |
| Release / operations | DevOps | PMO, Observability | ampliar DevOps |
| Support / incident intake | Triage | Observability, DevOps | ampliar Triage |
| Performance | Performance | Database, Backend, Frontend, Observability | ya cubierto |
| Documentación durable | Documentation | dueño del contenido | ya cubierto |
| QA funcional final | Humano | Testing, Reviewer | permanece fuera de agentes |

## Business analysis

No se crea Agent Business Analyst.

Product absorbe:

- descubrimiento;
- stakeholders;
- necesidades;
- reglas de negocio;
- alcance;
- requisitos funcionales;
- requisitos no funcionales.

PMO comienza cuando la definición necesita convertirse en backlog y ejecución.

## Accesibilidad

W3C distribuye accesibilidad entre producto, diseño, desarrollo y testing. Agent
Dev Kit sigue el mismo principio sin crear Agent Accessibility:

- Product expresa la necesidad/requisito;
- UX/UI es dueño del diseño accesible;
- Frontend implementa;
- Testing automatiza lo determinístico y prepara los checks;
- QA humano cubre evaluación funcional/manual que la automatización no puede
  demostrar.

## Privacy y compliance

No se crea Agent Compliance en v0.1.0.

Separación:

- Product/política externa indica qué obligación aplica;
- Security traduce la obligación en controles técnicos y evidencia;
- Database/Data implementan lifecycle, minimización, retención, borrado o
  de-identificación cuando corresponda;
- Documentation conserva evidencia durable cuando sea necesaria.

Security no brinda asesoramiento legal ni inventa regulación.

Si en el futuro Agent Dev Kit se usa en entornos regulados donde compliance sea
una disciplina independiente y recurrente, se reevaluará un agente opcional.

## Reliability / SRE

No se crea Agent SRE.

Observability absorbe la responsabilidad de reliability orientada a señales:

- SLIs;
- SLOs;
- error-budget style signals cuando aporten valor;
- alertas;
- incident detection;
- coordinación y diagnóstico;
- evidencia/timeline;
- post-incident learning.

DevOps mantiene ejecución operativa, despliegue, rollback y recovery.

Performance mantiene optimización medible.

PMO convierte follow-ups durables en backlog.

## Platform engineering

No se crea Agent Platform.

DevOps absorbe:

- workflows reutilizables;
- developer self-service cuando exista necesidad repetida;
- CI/CD;
- ambientes;
- deployment;
- release;
- rollback/recovery.

Architecture interviene cuando la plataforma introduce límites, servicios o
decisiones estructurales.

## Soporte e incidentes

Triage sólo hace intake y clasificación.

No se convierte en mesa de ayuda general ni diagnostica.

Flujo típico:

```text
reporte / incidente
        ↓
      Triage
        ↓
 Observability ── diagnosis
        ↓
 DevOps / especialista técnico ── remediation
        ↓
       PMO ── follow-up durable si corresponde
```

## Documentación

Documentation no es dueño de las decisiones funcionales o técnicas.

- Product es dueño del contenido funcional;
- Architecture/especialistas son dueños del contenido técnico;
- Documentation consolida, sincroniza y preserva artefactos durables.

Los gates concretos de cuándo participa cada agente están implementados por la orquestación por riesgo iniciada en M-028 y endurecida por las policies determinísticas posteriores.

## Regla para futuros agentes

Un nuevo agente requiere demostrar simultáneamente:

1. responsabilidad recurrente no cubierta;
2. entregable propio;
3. criterios claros de activación;
4. límites/handoffs distintos;
5. suficiente volumen de trabajo como para justificar el costo de coordinación.

Si una responsabilidad puede agregarse coherentemente a un rol existente, se
prefiere ampliar ese rol.
