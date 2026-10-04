# Interfaz MCP para clientes de chat

## Objetivo

Permitir que un cliente de IA compatible con Model Context Protocol (MCP)
utilice Agent Dev Kit sin duplicar la lógica del framework.

La arquitectura queda:

```text
Cliente de chat
(ChatGPT / Claude / Gemini / otro host MCP)
          ↓
          MCP
          ↓
AgentDevKitGateway
          ↓
runtime / Triage / DAG / preferencias
          ↓
proyecto consumidor
```

## Cliente de chat vs proveedor de agentes

Son decisiones independientes.

Ejemplo:

```text
Claude como cliente
      ↓ MCP
Agent Dev Kit
      ↓
OpenAI como provider interno
```

o:

```text
ChatGPT como cliente
      ↓ MCP
Agent Dev Kit
      ↓
otro provider registrado
```

El cliente desde el que el usuario conversa no determina qué modelo ejecuta
los agentes internos.

## Instalación

MCP es una dependencia opcional:

```bash
pip install -e ".[mcp]"
```

Si además se utilizará el provider OpenAI incluido:

```bash
pip install -e ".[openai,mcp]"
```

## Servidor local por stdio

Desde el proyecto consumidor:

```bash
agent-dev-kit mcp .
```

Este modo es apropiado para hosts MCP que pueden iniciar un proceso local.

## Streamable HTTP local

```bash
agent-dev-kit mcp . \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8000
```

El endpoint MCP queda en:

```text
http://127.0.0.1:8000/mcp
```

## Seguridad

### Proyecto fijo

El proyecto consumidor se selecciona al iniciar el servidor.

Las herramientas MCP no aceptan un `project_root`.

Por lo tanto un modelo conectado no puede cambiar de repositorio pasando una
ruta arbitraria.

### HTTP no público en v0.1.0

Agent Dev Kit rechaza bind directo a interfaces no-loopback como:

```text
0.0.0.0
```

La razón es evitar publicar accidentalmente un runtime con capacidad de actuar
sobre un repositorio.

Para clientes remotos se debe utilizar:

- un túnel MCP confiable;
- o un reverse proxy/autenticación administrada por el entorno de despliegue.

El servidor de desarrollo no debe exponerse directamente a Internet.

### Datos expuestos

`agent_dev_kit_status` devuelve:

- nombre del proyecto;
- directorio lógico, no ruta absoluta;
- stack;
- agentes habilitados;
- provider primario;
- nombres de fallbacks;
- política de fallback.

No devuelve `provider.options`, claves API ni otros secretos.

## Herramientas MCP

### agent_dev_kit_status

Inspecciona el proyecto al que está conectado el servidor.

### agent_dev_kit_chat

Envía un mensaje a una conversación persistente.

Devuelve un `session_id` que el cliente debe reutilizar en los siguientes
turnos.

### agent_dev_kit_chat_fallback

Aprueba o rechaza un cambio de provider cuando la conversación quedó bloqueada
por cuota, rate limit o indisponibilidad.

El cambio nunca es silencioso.

### agent_dev_kit_chat_reset

Descarta una conversación y su transcript neutral.

### agent_dev_kit_task

Solicita una tarea multi-especialista.

El gateway:

1. pide a Triage el DAG;
2. valida agentes habilitados;
3. ejecuta dependencias;
4. conserva resultados parciales;
5. devuelve evidencia.

### agent_dev_kit_task_fallback

Aprueba o rechaza el fallback de una tarea conservando el DAG y los nodos ya
completados.

### agent_dev_kit_task_status

Consulta el estado actual de un DAG.

## Storytime

El usuario escribe desde su cliente habitual:

> El reporte de progreso tiene datos incorrectos y la pantalla necesita una
> mejora de UX.

El cliente llama:

```text
agent_dev_kit_task
```

Agent Dev Kit construye:

```text
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

Si Backend agota la cuota del provider:

```text
Agent Dev Kit
    ↓
fallback_required
    ↓
cliente pregunta al usuario
    ↓
usuario aprueba
    ↓
agent_dev_kit_task_fallback
    ↓
continúa desde Backend
```

Architecture, Database y UX/UI no vuelven a ejecutarse.

## Compatibilidad

MCP es la frontera estándar del framework.

Un producto de chat concreto puede tener requisitos propios de plan,
configuración, permisos, túnel o despliegue. Esos requisitos pertenecen al
cliente, no al núcleo de Agent Dev Kit.

Esto permite conservar la misma interfaz aunque el usuario cambie de ChatGPT a
Claude, Gemini u otro host compatible con MCP.
