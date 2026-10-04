# Changelog

Todos los cambios relevantes de Agent Dev Kit se documentan en este archivo.

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

- Triage como punto de entrada;
- grafo permanente de capacidades/handoffs;
- DAG específico por tarea;
- dependencias y nodos ejecutables;
- bloqueo explícito si falta un especialista habilitado;
- Testing, Reviewer y Documentation dentro del flujo;
- QA funcional final humano.

### Orquestación eficiente

- subgrafo mínimo suficiente por tarea;
- gates explícitos para todas las responsabilidades;
- rechazo determinístico de especialistas sin gate/override;
- fases temporales por nodo para permitir participaciones múltiples justificadas;
- contexto mínimo por especialista mediante request summary + dependencias directas;
- plantillas funcionales/técnicas configurables por proyecto;
- trazas estructuradas con fingerprint, decisiones, DAG, duración, contexto y tokens cuando estén disponibles;
- pedido original no persistido por defecto;
- telemetría JSONL local opcional y fuera de Git;
- propuestas de Issues por patrones repetidos sin auto-modificar el framework.

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
- reanudación de DAG desde nodos pendientes.

### MCP

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

### Calidad

- documentación individual de los 16 agentes;
- documentación funcional y técnica;
- suite automatizada;
- smoke test end-to-end estilo Librería Inglés;
- GitHub Actions CI.

### Limitaciones conocidas

- OpenAI es el único provider concreto incluido de fábrica en v0.1.0;
- otros providers requieren registrar un adaptador;
- Streamable HTTP se limita a loopback: acceso remoto requiere túnel MCP
  confiable o proxy autenticado;
- publicación en un índice de paquetes queda para una etapa posterior.
