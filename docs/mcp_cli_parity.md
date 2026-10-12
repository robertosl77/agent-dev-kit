# Paridad CLI/MCP — desarrollo en `feat/mcp-cli-parity`

## Arquitectura

Las interfaces CLI y MCP ejecutan el **mismo** `DevAgentKit`, `ProviderRuntime`, `Workspace`, `TaskFacts` y `GitMutationGateway`. Las operaciones que no necesitan interfaz interactiva viven en `task_workflow.py`: controles previos, hechos verificables, veredicto, creación de rama, revisión del diff y commit. La CLI conserva la presentación y sus confirmaciones locales; `WorkflowController` (en `workflow_gateway.py`) representa cada pausa como una decisión pendiente que el cliente MCP debe presentar a una persona.

La interfaz anterior (`agent_dev_kit_task`, chat y fallback de chat/tarea) se conserva para compatibilidad. Para nuevos clientes, preferir `agent_dev_kit_workflow_*`.

## Nuevas herramientas MCP

- `agent_dev_kit_workflow_start(request, mode, issue?)`: modos `plan`, `propose`, `act`.
- `agent_dev_kit_workflow_status(workflow_id)`: estado, grafo, decisiones, resultado y diff.
- `agent_dev_kit_workflow_decide(workflow_id, decision_id, approve)`: una aprobación/rechazo por etapa; el identificador es de un solo uso.
- `agent_dev_kit_workflow_issue(workflow_id, issue)`: proporcionar referencia de issue cuando la política lo exige.
- `agent_dev_kit_workflow_fallback(workflow_id, approve)`: decidir fallback específico de esta tarea.
- `agent_dev_kit_workflow_cancel(workflow_id)`: terminar el workflow, sin descartar cambios locales.
- `agent_dev_kit_workflow_usage(workflow_id)`: consumo por llamada y costo estimado si hay precios configurados.
- `agent_dev_kit_repo_status()`: rama actual, cambios y resumen de diff.
- `agent_dev_kit_graphs(limit)`: trazas históricas resumidas.
- `agent_dev_kit_candidates()`: análisis de patrones de orquestación.

### Flujos

`mode=plan`: Triage planifica y retorna el grafo sin ejecutarlo.

`mode=propose`: inspección real del repositorio con herramientas de solo lectura y hechos verificables; si interviene Scrum Master, se presenta la historia de usuario y se requiere aprobación explícita antes de los demás agentes.

`mode=act`: el servidor debe haber habilitado acciones expresamente; verifica repo limpio, issue y rama base actualizada. Luego requiere **aprobación del plan**, **aprobación de historia** (si aplica), crea la rama de trabajo, ejecuta nodos con permisos de acción, verifica evidencias, muestra diff y consumo y requiere **aprobación del commit**. No hace push.

Cada decisión tiene su propio identificador `decision_id`. Aprobar el plan **no** aprueba la historia, la ejecución de un comando restringido o el commit. Si un archivo cambia después de revisar el diff, se requiere una nueva aprobación.

## Activación de acciones

Por seguridad, el modo `act` está apagado por defecto. Solo habilitar en un servidor de confianza:

```bash
agent-dev-kit mcp . --allow-actions
```

Para HTTP, conservar el bind local (`127.0.0.1`). Un cliente externo exige una frontera autenticada de confianza (túnel/proxy configurado correctamente). El identificador de decisión evita reusar una aprobación, pero **no prueba por sí mismo la identidad del usuario**: el host autenticado debe obtener consentimiento humano explícito para cada llamada de aprobación.

Los comandos de tests automáticos declarados por el proyecto siguen funcionando. Los comandos que requieren confirmación individual en `workspace.allowed_commands` se **rechazan** en el controlador MCP hasta contar con un protocolo confiable de autorización de ejecución en mitad de un nodo. No se otorgan permisos permanentes. Los comandos permitidos dejan de ejecutarse con `shell=True`; se interpretan en argv, sin operadores de shell.

## Limitaciones de esta etapa

- El estado de workflow está en memoria (TTL del Gateway). Un reinicio pierde la capacidad de reanudar tareas pendientes.
- Solo se permite **una** tarea de acción activa por proceso MCP/Workspace; no hay lock distribuido entre procesos diferentes.
- Sin escritura automática de GitHub Issues, push, creación remota de PR ni merges.
- Los diffs de más de 50.000 caracteres y archivos nuevos binarios no se pueden aprobar por MCP y requieren revisión/commit local.
- El contrato existente `agent_dev_kit_task` sigue siendo histórico; usar `workflow_start` para paridad.
- `read_issue` usa anónimo si el repo es público; la solicitud interactiva de un token para repos privados todavía pertenece a CLI.
- Persistencia de estados y autorizaciones de comandos deben resolverse antes de declarar **paridad total**.

## Validación

```bash
git switch feat/mcp-cli-parity
git pull
python -m pip install -e ".[dev]"
pytest -q
```

Tests especialmente relevantes: `tests/test_workflow_gateway.py`, `tests/test_mcp_server.py`, `tests/test_workspace_tools.py` y `tests/test_console_modes.py`.

Luego abrir MCP y verificar `agent_dev_kit_workflow_start` primero con `mode=plan` y `mode=propose`, sin efectos de escritura. Habilitar `--allow-actions` solo en un repositorio de pruebas, no en un directorio de trabajo con cambios importantes.
