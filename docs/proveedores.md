# Proveedores de agentes/modelos

## Objetivo

Agent Dev Kit no debe quedar acoplado a una empresa ni a un SDK concreto.

La arquitectura base es:

```text
Agentes del framework
        ↓
contrato AgentProvider
        ↓
ProviderRegistry
        ├── OpenAIProvider
        ├── CopilotProvider     (futuro)
        ├── ClaudeProvider      (futuro)
        └── otros
```

## Regla

Los archivos de agentes no deben importar directamente SDKs de OpenAI, Microsoft, Anthropic u otros proveedores.

Solo el adaptador concreto conoce su SDK.

## Configuración por proyecto

El proyecto consumidor decide el proveedor:

```python
from agent_dev_kit import ProviderConfig, build_default_registry

config = ProviderConfig(
    provider="openai",
    default_model=None,
)

provider = build_default_registry().create(config)
```

Más adelante otro proyecto podría registrar un proveedor distinto sin modificar Agent Product, Backend, UX/UI, PMO, etc.

## OpenAI

La primera implementación concreta es `OpenAIProvider`.

Está aislada en:

```text
src/agent_dev_kit/providers/provider_openai.py
```

El adaptador encapsula las primitivas del OpenAI Agents SDK y normaliza:

- creación de agentes;
- handoffs;
- ejecución async;
- ejecución sync;
- salida final;
- agente que quedó activo.

Para instalar este proveedor:

```bash
pip install -e ".[openai]"
```

## Política de compatibilidad del SDK OpenAI

La serie `v0.1.x` declara compatibilidad con `openai-agents>=0.23.1,<0.24`.
Los patches dentro de esa línea pueden resolverse automáticamente. Un salto de
minor o major requiere una actualización explícita del rango y debe pasar el
job `Agent Dev Kit CI / openai-provider`.

Ese job instala `.[dev,openai,mcp]` y ejecuta un smoke/contract test real del
adaptador: creación de agentes, handoffs, structured output y normalización de
ejecución sync/async. Los tests sustituyen el Runner por un fake al ejecutar, de
modo que validan la API del SDK sin consumir credenciales ni hacer llamadas de
red.

## Proveedores futuros

Copilot y Claude quedan previstos como adaptadores futuros. Incorporarlos no debe obligar a reescribir los agentes del catálogo.

## Qué no resuelve esta capa

Esta capa no decide:

- qué agentes existen;
- cuáles están habilitados;
- qué prompt usa cada rol;
- qué stack usa el proyecto;
- qué herramientas tiene cada agente;
- cómo se guarda la configuración del proyecto consumidor.

Esas responsabilidades pertenecen a otras capas/modernizaciones.
