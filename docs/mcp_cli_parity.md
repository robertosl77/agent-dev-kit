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
- `agent_dev_kit_workflow_resume(workflow_id, approve)`: reintento explícito de fases seguras luego de una interrupción; nunca vuelve a ejecutar automáticamente una escritura interrumpida.
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

Los comandos de tests automáticos declarados por el proyecto siguen funcionando. Cuando un agente solicita un comando declarado en `workspace.allowed_commands`, el comando **no se ejecuta durante la llamada al modelo**. Se registra como pendiente (sin duplicados) y se devuelve al modelo el aviso de que no se ejecutó. Al terminar el DAG, el Gateway presenta cada solicitud por separado con `approval.kind=command`. La persona autoriza o rechaza **el comando exacto y el directorio de trabajo**; si se autoriza, se ejecuta una sola vez. Una denegación, un error o un exit code distinto de cero bloquea el commit. El modelo no recibe retroactivamente la salida del comando; el resultado queda en la evidencia de revisión y la persona debe revisar la validación. No existen permisos permanentes. El comando se ejecuta con `shell=False`, sin operadores de shell.

**Recuperación (etapa 2).** Los checkpoints JSON privados y atómicos se guardan **fuera del repositorio consumidor**, en `%LOCALAPPDATA%/agent-dev-kit/mcp-workflows/<hash-del-proyecto>` en Windows o `$XDG_STATE_HOME/agent-dev-kit/mcp-workflows/<hash-del-proyecto>` (por defecto `~/.local/state`) en Linux/macOS. Se puede definir `AGENT_DEV_KIT_STATE_HOME` para elegir otro directorio base. Incluyen el plan, estados y salidas de nodos terminados, progreso/consumo, solicitudes de comandos, aprobaciones pendientes y revisión del diff; son datos potencialmente sensibles, **no deben publicarse**. No se escriben claves de proveedores. Se mantienen por el TTL configurado para el Gateway; al reabrir una sesión, los identificadores de aprobación anteriores se invalidan y se generan otros nuevos. Una interrupción en un nodo de solo lectura exige `workflow_resume(approve=true)`; se retoman los nodos terminados del DAG y se reintenta solo lo pendiente. Una interrupción durante creación de rama, comando, escritura o commit **no se reproduce**, y requiere revisión local manual. Solo un proceso servidor debe usar un repositorio; no hay coordinación distribuida entre procesos.

## Limitaciones de esta etapa

- Hay recuperación durable de checkpoints y permisos pendientes, pero **no** continuación transparente de una llamada del modelo interrumpida ni repetición automática de acciones. Los workflows con escrituras parciales requieren revisión manual.
- Solo se permite **una** tarea de acción activa por repositorio/servidor, y se bloquea una nueva tarea cuando existe un checkpoint de acción sin cerrar. No hay lock distribuido entre procesos diferentes.
- Sin escritura automática de GitHub Issues, push, creación remota de PR ni merges.
- Los diffs de más de 50.000 caracteres y archivos nuevos binarios no se pueden aprobar por MCP y requieren revisión/commit local.
- El contrato existente `agent_dev_kit_task` sigue siendo histórico; usar `workflow_start` para paridad.
- `read_issue` usa anónimo si el repo es público; la solicitud interactiva de un token para repos privados todavía pertenece a CLI.
- La autorización de comandos MCP se ejecuta **después** de finalizar el nodo que la pidió, no dentro del mismo turno del modelo; falta integrar una continuación que consuma el resultado de manera conversacional antes de declarar **paridad total**.
- Falta validar los checkpoints y permisos con el MCP real en Windows, y definir la integración de identidad de usuario/capacidades remotas con un servidor autenticado.

## Validación

```bash
git switch feat/mcp-cli-parity
git pull
python -m pip install -e ".[dev]"
pytest -q
```

Tests especialmente relevantes: `tests/test_workflow_gateway.py`, `tests/test_mcp_server.py`, `tests/test_workspace_tools.py` y `tests/test_console_modes.py`.

Luego abrir MCP y verificar `agent_dev_kit_workflow_start` primero con `mode=plan` y `mode=propose`, sin efectos de escritura. Habilitar `--allow-actions` solo en un repositorio de pruebas, no en un directorio de trabajo con cambios importantes.
