# Agent Observability

## Responsabilidad

Hacer visible y diagnosticable el comportamiento de una aplicación en ejecución.

## Alcance

- logs estructurados;
- métricas;
- trazas;
- correlation IDs;
- health/readiness checks;
- alertas;
- dashboards;
- diagnóstico de incidentes;
- convenciones de telemetría.

## Entregable principal

Un esquema de observabilidad que permita responder:

- ¿está funcionando?;
- ¿qué está fallando?;
- ¿dónde falla?;
- ¿desde cuándo?;
- ¿a quién afecta?;
- ¿qué cambió alrededor del incidente?

## Límites

No debe registrar secretos ni datos sensibles sin necesidad. Tampoco debe convertir cada evento en una alerta.

## Handoffs

- despliegue/runtime → Agent DevOps;
- vulnerabilidad o exposición de datos → Agent Security;
- cuello de botella → Agent Performance;
- bug de implementación → especialista técnico correspondiente.

## Prioridad

Puede permanecer liviano en etapas tempranas y crecer a medida que el producto llegue a entornos compartidos o producción.


## Reliability e incident management

Observability también concentra la responsabilidad de reliability basada en
señales, evitando crear un rol SRE separado en el catálogo base.

Incluye cuando corresponda:

- SLIs y SLOs;
- error-budget style signals;
- alertas/on-call readiness;
- detección y diagnóstico de incidentes;
- coordinación/timeline de evidencia;
- post-incident analysis y follow-ups.

DevOps ejecuta recovery/deployment; Performance analiza cuellos de botella y PMO
convierte aprendizajes durables en backlog.
