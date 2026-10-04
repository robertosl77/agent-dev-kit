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
DAG

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

## Agente deshabilitado

Un segundo escenario deshabilita UX/UI.

Triage identifica que la responsabilidad es necesaria y la ejecución queda bloqueada con `DisabledAgentRequiredError`.

Frontend no sustituye a UX/UI.

## Costo

El smoke test usa providers falsos.

No consume tokens ni APIs externas.

## Criterio de salida

M-022 se considera completada únicamente cuando este escenario pasa dentro de GitHub Actions junto con toda la suite.
