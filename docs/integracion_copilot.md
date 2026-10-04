# Integración de GitHub Copilot con Agent Dev Kit

## Estado de la decisión

M-029 define arquitectura, no implementación específica.

Decisión para la línea posterior a v0.1.0:

~~~text
GitHub Copilot
      ↓
Copilot Custom Agent (opcional)
      ↓
MCP
      ↓
Agent Dev Kit Gateway
      ↓
Orquestador Agent Dev Kit
      ↓
Runtime / especialistas
~~~

Cuando Agent Dev Kit se ejecute como servicio remoto y necesite acceder a un repositorio corporativo:

~~~text
GitHub Copilot
      ↓
Custom Agent opcional
      ↓
MCP
      ↓
Agent Dev Kit Service
      ↓
GitHub App
      ↓
Repositorio autorizado
~~~

MCP, Custom Agent y GitHub App no son tres soluciones excluyentes. Son capas distintas.

## Objetivo

Permitir que Copilot sea un cliente de Agent Dev Kit sin duplicar el orquestador, convertir Copilot en un provider interno obligatorio, acoplar el framework a una única interfaz de chat ni romper compatibilidad con otros hosts compatibles con MCP.

## Alternativa 1 — MCP como integración base

Agent Dev Kit ya expone una interfaz cliente-neutral mediante src/agent_dev_kit/mcp_server.py y src/agent_dev_kit/gateway.py.

El host externo invoca herramientas de Agent Dev Kit. El Gateway mantiene la frontera del proyecto y el Runtime conserva la responsabilidad de ejecutar el DAG.

### Ventajas

- reutiliza infraestructura existente;
- mantiene el framework independiente del cliente;
- no duplica contratos de ejecución;
- la misma interfaz puede ser utilizada por múltiples hosts;
- permite evolucionar Agent Dev Kit sin crear una implementación por cliente.

### Riesgos / límites

- cada host decide qué variantes de MCP soporta;
- el transporte remoto necesita autenticación y red segura;
- un host puede tener su propio comportamiento agentic, por lo que debe quedar claro que la planificación interna pertenece a Agent Dev Kit.

### Decisión

**MCP es la interfaz base soportada para Copilot.**

No se agrega un protocolo Copilot-específico al núcleo.

## Alternativa 2 — Copilot Custom Agent

GitHub permite definir custom agents mediante perfiles Markdown. El perfil puede definir instrucciones, herramientas y servidores MCP.

Esto permite construir un adaptador fino de experiencia:

~~~text
.github/agents/agent-dev-kit.agent.md
             ↓
orienta a Copilot a usar las herramientas MCP de Agent Dev Kit
             ↓
MCP
             ↓
Agent Dev Kit
~~~

### Responsabilidad del Custom Agent

Puede orientar al usuario hacia Agent Dev Kit, limitar el conjunto de herramientas visibles y explicar cuándo delegar una tarea completa al framework.

No debe reconstruir el DAG, duplicar los gates de orchestration.py, reimplementar especialistas ni mantener una segunda política de routing.

### Decisión

**Custom Agent es un adaptador opcional sobre MCP**, no el núcleo de la integración.

Su implementación concreta queda para una versión posterior a v0.1.0.

## Alternativa 3 — GitHub App

Una GitHub App resuelve otro problema: acceso autorizado al repositorio. Es especialmente relevante para M-027 cuando Agent Dev Kit se ejecute fuera del entorno consumidor.

La instalación puede limitarse a repositorios concretos y los installation access tokens pueden reducir permisos y repositorios dentro de lo concedido a la instalación. Estos tokens son temporales.

### Responsabilidad de GitHub App

- autenticar Agent Dev Kit Service frente a GitHub;
- limitar repositorios accesibles;
- limitar permisos;
- recibir webhooks cuando corresponda;
- actuar con identidad de aplicación en lugar de credenciales personales de larga duración.

### Lo que NO resuelve

GitHub App no define por sí sola cómo Copilot conversa con Agent Dev Kit, cómo se construye el DAG, cómo se seleccionan especialistas ni cómo funciona el Gateway.

### Decisión

**GitHub App pertenece principalmente a la arquitectura de distribución remota de M-027.**

Puede coexistir con MCP, pero no reemplazarlo como interfaz cliente.

## ¿Necesitamos un provider interno Copilot?

No para el caso de integración como cliente.

El concepto de provider dentro de Agent Dev Kit representa el motor que ejecuta los agentes internos. Copilot actuando como host/cliente está en la otra cara de la arquitectura.

Agregar un CopilotProvider sólo tendría sentido si en el futuro existiera un contrato soportado para usar Copilot como motor interno de inferencia. Eso es independiente de integrarlo como frontend.

## Evitar doble orquestación

El riesgo principal es permitir que Copilot descomponga una tarea en especialistas y, luego, Agent Dev Kit vuelva a descomponerla.

Regla:

> Cuando una tarea se entrega a Agent Dev Kit como tarea orquestada, el DAG, gates, fases, especialistas y trazabilidad pertenecen al orquestador de Agent Dev Kit.

El host puede decidir si invoca Agent Dev Kit, pero no debe reconstruir su plan interno.

~~~text
Usuario
  ↓
Copilot decide usar ADK
  ↓
agent_dev_kit_task(...)
  ↓
Triage ADK
  ↓
gates
  ↓
DAG
  ↓
especialistas
~~~

## Relación con el código actual

- mcp_server.py: frontera de protocolo; debe seguir neutral al cliente.
- gateway.py: frontera segura del proyecto.
- orchestration.py: fuente de verdad de gates y trazabilidad.
- task_plan.py: contrato del DAG.
- runtime.py: ejecución del plan y evidencia.
- provider_registry.py: providers internos; no mezclar con elección del cliente externo.

## Alcance de v0.1.0

v0.1.0 debe incluir la interfaz MCP neutral existente, esta decisión documentada y una arquitectura compatible con Copilot sin código específico.

v0.1.0 NO necesita incluir perfil Custom Agent listo para instalar, GitHub App, servicio SaaS, provider Copilot ni automatización de instalación de Copilot.

## Roadmap sugerido

### v0.2.x

- prototipo de Custom Agent fino sobre MCP;
- prueba con repositorio consumidor de laboratorio;
- validar límites de herramientas y experiencia de uso;
- documentar configuración por host.

### v0.2.x / v0.3.x junto con M-027

- endpoint MCP remoto autenticado;
- GitHub App;
- aislamiento por consumidor;
- permisos mínimos;
- telemetría y auditoría;
- prueba corporativa controlada.

## Referencias externas

Documentación oficial consultada:

- GitHub Copilot custom agents: https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-custom-agents
- Custom agents / sub-agent orchestration: https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/custom-agents
- Instalación de GitHub Apps: https://docs.github.com/en/apps/using-github-apps/installing-a-github-app-from-a-third-party
- Autenticación como instalación: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation
- SAML y GitHub Apps: https://docs.github.com/en/enterprise-cloud@latest/apps/using-github-apps/saml-and-github-apps
