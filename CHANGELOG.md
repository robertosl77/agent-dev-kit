# Changelog

Todos los cambios relevantes de Agent Dev Kit se documentan en este archivo.

## [0.2.0] — multi-proveedor por consola

Issue: M-073 (#114), subtarea de M-056 (#97).

### Proveedores

- `AnthropicProvider` con la librería oficial `anthropic` (extra `[anthropic]`);
- `GeminiProvider` con la librería oficial `google-genai` (extra `[gemini]`);
- ciclo de agente propio para ambos (`providers/tool_loop.py`): derivación entre
  agentes con herramientas `transfer_to_<agente>`, salida estructurada del
  planner con herramienta forzada y JSON Schema, herramientas del proyecto con
  `FunctionTool`;
- `OpenAIProvider` acepta la key y el modelo en tiempo de ejecución;
- `build_default_registry(credentials)` recibe las keys en memoria, sin
  variables de entorno;
- catálogo `BUILTIN_PROVIDERS` (extra, variables de entorno y URL de la key).

### Consola

- menú antes de `run` y `task`: proveedor, key y modelo en cada ejecución;
- la key se pide oculta y **no se guarda**; si existe la variable de entorno del
  proveedor, se usa sin preguntar;
- `provider.name` de `project.yaml` pasa a ser el **proveedor preferido**
  (Enter); los `project.yaml` existentes siguen funcionando sin cambios;
- modelo siempre elegido de la **lista en vivo** del proveedor
  (`list_models`), sin modelo preferido; carga manual si la lista falla;
- etiquetas de modelo solo con lo que informa el proveedor (`piensa`, `línea`);
- `--provider` y `--model` para uso no interactivo;
- los errores muestran la causa original resumida y sin secretos.

### Errores

- clasificación de errores de Anthropic (sin crédito, key inválida, límite,
  sobrecarga) y Gemini (key inválida, `RESOURCE_EXHAUSTED`);
- falta de key informada como `ProviderAuthenticationError`.

### Cambios de comportamiento

- `agent-dev-kit run` y `task` ahora preguntan proveedor y modelo antes de
  empezar. Para el comportamiento anterior sin menú:
  `--provider openai --model <modelo>` con `OPENAI_API_KEY` definida.
- MCP y API Python no cambian: usan el proveedor de `project.yaml`. Anthropic y
  Gemini requieren `provider.default_model` en ese modo.

### Documentación

- `docs/proveedores.md` reescrito;
- README actualizado;
- incluye el diagrama de arquitectura (`docs/arquitectura_agent_dev_kit.*`)
  publicado en `develop` después de `v0.1.0`.

## [0.1.0] — primera versión utilizable

### Framework

- catálogo físico de 16 agentes por responsabilidad;
- capa neutral de providers;
- provider OpenAI como primera implementación concreta;
- configuración nativa y contextual por proyecto consumidor;
- activación/desactivación estricta de agentes;
- contexto del stack inyectado a los especialistas;
- tools/capabilities asignables por agente.

### Coordinación

- orquestación por riesgo con subgrafo mínimo suficiente;
- decisión explícita de inclusión/omisión para cada especialista habilitado;
- gates determinísticos para riesgos y artefactos durables;
- preclasificación independiente de riesgos críticos, además de la clasificación de Triage;
- contratos estrictos para risk flags, fases y artefactos durables;
- policies determinísticas por proyecto que sólo pueden endurecer el routing;
- planner Triage aislado sin handoffs/tools y structured output real cuando el provider lo soporta;
- schema estricto de `TaskPlan` con un único intento controlado de reparación;
- fases explícitas por nodo (discovery/design/implementation/validation/documentation/release);
- budgets duros para tamaño del DAG, provider calls, revisitas, contexto y evidencia;
- reutilización intra-task de outputs equivalentes y deduplicación/truncado local de contexto;
- contexto reducido por nodo en lugar de reenviar el pedido completo;
- trazas estructuradas con fingerprint, llamadas, revisitas y duración;
- trazas con sandbox de path, retención, lectura incremental, locking y persistencia de estados no exitosos;
- telemetría runtime local no versionada;
- candidatos de mejora derivados de evidencia, siempre con revisión humana;
- plantillas configurables para especificaciones funcionales/técnicas y otros artefactos;

- Triage como punto de entrada;
- grafo permanente de capacidades/handoffs;
- DAG específico por tarea;
- dependencias y nodos ejecutables;
- bloqueo explícito si falta un especialista habilitado;
- Testing, Reviewer y Documentation dentro del flujo;
- QA funcional final humano.

### Preferencias

- perfil global persistente dentro de Agent Dev Kit;
- preferencias por agente;
- exclusiones por proyecto;
- overrides contextuales;
- observaciones que pueden convertirse en candidatas;
- confirmación humana antes de promover una candidata a regla permanente.

### Ejecución

- API Python;
- CLI interactivo;
- ejecución de tareas multi-especialista;
- errores de provider normalizados;
- cuota/rate limit/indisponibilidad;
- fallback explícito con aprobación;
- reanudación de DAG desde nodos pendientes;
- máquina de estados explícita del Gateway para planning/execution/fallback/blocked/failed/completed;
- estado `requires_human_approval` ante exceso de budgets;
- TTL por inactividad y límite total configurable de sesiones del Gateway.

### MCP

- decisión de arquitectura para Copilot como cliente vía MCP;
- Custom Agent definido como adaptador opcional sobre MCP, sin duplicar el orquestador;
- GitHub App separada como mecanismo de acceso remoto al repositorio para M-027;
- gateway neutral de cliente;
- servidor MCP v2;
- transporte stdio;
- Streamable HTTP local;
- sesiones de conversación;
- herramientas de tarea y estado;
- aprobación separada de fallback;
- proyecto fijado al iniciar el servidor;
- rechazo de bind HTTP público directo en v0.1.0.

### Git workflow

- enforcement obligatorio de mutaciones Git soportadas mediante `GitMutationGateway`;
- override humano reemplazado por autorización scoped + verificador externo;
- registro explícito de tools Git mutantes con política `git_policy_guard`;
- política Git configurable por proyecto consumidor;
- `main`/producción y rama de integración separadas;
- ramas de tarea obligatoriamente creadas desde integración;
- PR de tarea hacia integración y PR de release hacia producción;
- ramas protegidas contra escritura directa;
- excepción únicamente mediante autorización humana explícita;
- `GitPolicyGuard` determinístico para integraciones Git;
- recomendación de defensa en profundidad con Rulesets/Branch Protection.

### Seguridad

- Security como dueño explícito del riesgo y de los criterios de seguridad;
- security testing defensivo para injection, XSS, autorización/IDOR, path traversal, uploads y configuración;
- security regression automatizable mediante Testing;
- integración de SAST/SCA/secret scanning/container checks/DAST mediante DevOps cuando corresponda;
- Reviewer verifica evidencia y disposición de hallazgos bloqueantes;
- límites explícitos contra pruebas destructivas no autorizadas.

### Cobertura SDLC

- auditoría del catálogo contra NIST SSDF/DevSecOps, OWASP SAMM, Microsoft SDL, Google SRE, W3C ARRM y NIST Privacy Framework;
- se mantienen 16 agentes: no se agregan roles por organigrama;
- Product absorbe business analysis y requisitos no funcionales;
- UX/UI + Testing cubren accesibilidad;
- Security cubre privacy engineering y compliance técnico sin asumir asesoramiento legal;
- Observability incorpora SLIs/SLOs, reliability e incident management;
- DevOps incorpora platform engineering y release operations;
- Triage incorpora support/incident intake;
- Database/Data aplican lifecycle de datos definido por Product/Security.

### Distribución futura

- decisión arquitectónica de estrategia de distribución cerrada futura;
- servicio remoto + GitHub App recomendado para consumidores corporativos sin entrega de implementación;
- MCP definido como interfaz natural del servicio;
- artefacto local compilado reservado como alternativa offline/on-premise;
- implementación cerrada diferida a v0.2.0+.

### Calidad

- documentación individual de los 16 agentes;
- documentación funcional y técnica;
- suite automatizada;
- smoke test end-to-end estilo Librería Inglés;
- rango compatible explícito `openai-agents>=0.23.1,<0.24`;
- CI específico del provider OpenAI sin consumo de APIs externas;
- build de wheel + sdist e instalación del wheel en entorno limpio;
- smoke del artefacto distribuible: import, package data, CLI y MCP;
- GitHub Actions CI con jobs separados para suite, provider y package smoke.

### Limitaciones conocidas

- OpenAI es el único provider concreto incluido de fábrica en v0.1.0;
- otros providers requieren registrar un adaptador;
- Streamable HTTP se limita a loopback: acceso remoto requiere túnel MCP
  confiable o proxy autenticado;
- publicación en un índice de paquetes queda para una etapa posterior;
- las sesiones de conversación/tarea del Gateway son in-memory y se pierden al reiniciar el proceso;
- conversaciones largas todavía no aplican compaction/sliding window;
- nodos independientes del DAG se ejecutan secuencialmente en v0.1.0;
- métricas de tokens/costo reales dependen de una evolución posterior del contrato de providers.
