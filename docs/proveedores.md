# Proveedores de agentes/modelos

## Objetivo

Agent Dev Kit no debe quedar acoplado a una empresa ni a un SDK concreto.

Desde `v0.2.0` hay tres proveedores incluidos y se elige cuál usar **en cada
ejecución** (M-073):

```text
Agentes del framework
        ↓
contrato AgentProvider
        ↓
ProviderRegistry
        ├── OpenAIProvider      (openai-agents)
        ├── AnthropicProvider   (anthropic, librería oficial)
        ├── GeminiProvider      (google-genai, librería oficial)
        └── otros               (M-074: proveedor compatible OpenAI genérico)
```

## Regla

Los archivos de agentes no deben importar directamente SDKs de OpenAI, Microsoft, Anthropic u otros proveedores.

Solo el adaptador concreto conoce su SDK.

## Uso por consola

```text
> agent-dev-kit run .
¿Qué proveedor querés usar?
  1) Anthropic (Claude)
  2) Google Gemini
  3) OpenAI   (preferido)          ← provider.name de project.yaml (Enter)
> 1
La key se obtiene en: https://platform.claude.com/settings/keys
Pegá tu key de Anthropic (Claude) (no se muestra): ****
¿Qué modelo?                        ← lista en vivo del proveedor
  1) claude-opus-...      [línea opus]
  2) claude-haiku-...     [línea haiku]
> 2
you> ...
```

`agent-dev-kit task . "pedido"` usa el mismo menú.

Reglas del menú:

1. **Proveedor**: se listan todos los incluidos. `provider.name` de
   `.agent-dev-kit/project.yaml` es el **preferido** (se elige con Enter).
2. **Key**: se pide en cada ejecución con entrada oculta y **no se guarda en
   ningún lado**; vive en memoria mientras dura el proceso. Si existe la
   variable de entorno del proveedor, se usa sin preguntar.
3. **Modelo**: siempre se pregunta, con la **lista en vivo** del proveedor. No
   hay modelo preferido ni preseleccionado. Si la lista no se puede obtener, se
   escribe el nombre a mano.
4. **Etiquetas**: solo lo que informa el proveedor y además distingue modelos
   (Anthropic: `línea`). La capacidad de razonamiento no se muestra porque hoy
   la informan todos los modelos (M-075). No se deduce nada por el nombre.

Para scripts o CI, `--provider` y `--model` saltean el menú:

```bash
agent-dev-kit run . --provider anthropic --model claude-haiku-4-5
```

## Instalación

| Proveedor | Extra | Variable de entorno (opcional) | Dónde se obtiene la key |
|---|---|---|---|
| Anthropic | `agent-dev-kit[anthropic]` | `ANTHROPIC_API_KEY` | https://platform.claude.com/settings/keys |
| Gemini | `agent-dev-kit[gemini]` | `GEMINI_API_KEY` (o `GOOGLE_API_KEY`) | https://aistudio.google.com/apikey |
| OpenAI | `agent-dev-kit[openai]` | `OPENAI_API_KEY` | https://platform.openai.com/api-keys |

Todos juntos:

```bash
python -m pip install "agent-dev-kit[openai,anthropic,gemini] @ git+https://github.com/robertosl77/agent-dev-kit.git@v0.2.0"
```

Las APIs se pagan aparte de las suscripciones de chat: el crédito de claude.ai
o ChatGPT no sirve para la API. Gemini tiene un plan gratuito limitado.

## MCP y API Python

Sin menú. Se usa el proveedor preferido de `project.yaml` y su variable de
entorno. Anthropic y Gemini **exigen modelo** en ese modo:

```yaml
provider:
  name: anthropic
  default_model: claude-haiku-4-5
```

Desde Python la key se puede pasar sin variables de entorno:

```python
from agent_dev_kit import ProviderConfig, build_default_registry

registry = build_default_registry({"anthropic": key_ingresada})
provider = registry.create(
    ProviderConfig(provider="anthropic", default_model="claude-haiku-4-5")
)
```

## Cómo están implementados

### OpenAI

`providers/provider_openai.py` encapsula el OpenAI Agents SDK (creación de
agentes, handoffs, structured output, ejecución sync/async). Si la key llega
por el menú, se pasa explícitamente al SDK y se desactiva su exportación de
trazas.

### Anthropic y Gemini

Usan sus **librerías oficiales** directamente, sin el motor de OpenAI ni
intermediarios (M-073, decisión 4). El ciclo de agente lo implementa Agent Dev
Kit en `providers/tool_loop.py`:

```text
mensaje
  └─► llamada al modelo ──► solo texto ─────────────► resultado
                        ├─► transfer_to_<agente> ───► sigue el otro agente (derivación)
                        ├─► herramienta del proyecto ► ejecuta y sigue
                        └─► submit_output ──────────► resultado estructurado (planner)
```

- **Derivación** (modo conversación): cada handoff es una herramienta
  `transfer_to_<agente>`.
- **Salida estructurada** (planner): herramienta `submit_output` forzada, con el
  JSON Schema generado desde `StructuredTaskPlan`.
- **Herramientas del proyecto**: se registran como `FunctionTool` (nombre,
  descripción, parámetros y función) con `provider="anthropic"` o `"gemini"`.
- Gemini conserva el contenido nativo del modelo entre turnos para devolverle
  sus *thought signatures*.

## Errores

Los errores de cada SDK se normalizan a las mismas categorías:

| Situación | Error |
|---|---|
| Sin key | `ProviderAuthenticationError` ("No API key available…") |
| Key inválida | `ProviderAuthenticationError` |
| Sin crédito / cuota agotada (incluye Gemini gratis) | `ProviderQuotaExceeded` |
| Límite de pedidos | `ProviderRateLimited` |
| Caído, sobrecargado o sin red | `ProviderUnavailable` |

El CLI muestra además la causa original resumida y sin secretos.

## Compatibilidad de SDKs

| Extra | Rango |
|---|---|
| `openai` | `openai-agents>=0.23.1,<0.24` |
| `anthropic` | `anthropic>=1.11,<2` |
| `gemini` | `google-genai>=2.28,<3` |

Los tests de cada proveedor sustituyen el cliente por uno falso: validan la
integración con el SDK sin credenciales ni red.

## Qué no resuelve esta capa

Esta capa no decide:

- qué agentes existen;
- cuáles están habilitados;
- qué prompt usa cada rol;
- qué stack usa el proyecto;
- qué herramientas tiene cada agente;
- cómo se guarda la configuración del proyecto consumidor.

Esas responsabilidades pertenecen a otras capas/modernizaciones.
