# Smoke test end-to-end

## Objetivo

Antes de crear la primera versión estable, Agent Dev Kit debe probarse como un framework consumido por un proyecto externo.

El smoke test automatizado vive en:

```text
tests/test_smoke_e2e.py
```

## Story utilizada

El proyecto consumidor representa una configuración equivalente a Librería Inglés:

- backend Python/FastAPI;
- frontend Angular;
- UI Bootstrap;
- database SQLite.

La solicitud es:

> El reporte de progreso muestra datos incorrectos y además necesita una mejor experiencia de usuario.

## Recorrido

```text
project.yaml
    ↓
preferencias globales + proyecto
    ↓
agentes habilitados
    ↓
Triage
    ↓
perfil + gates por especialista
    ↓
validación determinística
    ↓
DAG mínimo con fases

              Architecture
              /          \
             ↓            ↓
        Database          UX/UI
             ↓              \
          Backend           \
             \               ↓
              └────────→ Frontend
                         ↓
                      Testing
                         ↓
                      Reviewer
                         ↓
                   Documentation
```

## Fallo de proveedor

El provider primario simulado agota cuota al llegar a Backend.

El test valida:

```text
Primary
  ↓
ProviderQuotaExceeded
  ↓
confirmación de fallback
  ↓
Backup
  ↓
reanuda desde nodos pendientes
```

Architecture, Database y UX/UI no vuelven a ejecutarse.

La traza del orquestador conserva intentos, revisitas, provider utilizado y
estado suficiente para verificar que la reanudación no repitió nodos ya
completados.

## Agente deshabilitado

Un segundo escenario deshabilita UX/UI.

Triage identifica que la responsabilidad es necesaria y la ejecución queda bloqueada con `DisabledAgentRequiredError`.

Frontend no sustituye a UX/UI.

## Orquestación por riesgo

El smoke test actual también valida el contrato de M-028:

- Triage devuelve perfil de solicitud;
- cada especialista habilitado tiene decisión explícita de inclusión/omisión;
- los riesgos declarados obligan a seleccionar sus responsables;
- los nodos incluyen fase;
- el runtime genera una traza estructurada;
- el fallback incrementa la revisita únicamente para el nodo que se reintenta;
- los especialistas reciben contexto acotado a resumen, objetivo y dependencias.

La aceptación funcional final continúa fuera del smoke automatizado y pertenece
al QA humano.

## Costo

El smoke test usa providers falsos.

No consume tokens ni APIs externas.

## Criterio de salida

Para el release v0.1.0, este escenario debe pasar dentro de GitHub Actions junto
con toda la suite en `development`, en el PR de release
`development → main` y finalmente sobre el commit de `main` que recibirá el
tag.
