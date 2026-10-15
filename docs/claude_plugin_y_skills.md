# Agent Dev Kit en Claude (sin servidor MCP)

Dos formas de usar el modelo de Agent Dev Kit dentro de Claude, generadas desde
las mismas definiciones del código (`src/agent_dev_kit/agents`, `routing.py`,
`orchestration_policy.py`).

```text
src/agent_dev_kit (fuente única)
        │
        └── scripts/build_claude_assets.py
                ├── plugins/agent-dev-kit/        → Claude Code (versionado)
                └── dist/claude-ai-skills/*.zip   → claude.ai (no versionado)
```

## Regenerar

```bash
PYTHONPATH=src python scripts/build_claude_assets.py
```

`tests/test_claude_assets.py` falla si el plugin versionado quedó desactualizado
respecto de los agentes.

## Claude Code — plugin

| Pieza | Qué es |
|---|---|
| `skills/orquestar` | Triage + planner: clasifica, arma el DAG, pide aprobación, ejecuta |
| `agents/adk-*.md` | 16 especialistas como subagentes (contexto propio) |
| Grafo | Cada especialista sólo consulta a sus vecinos del grafo permanente |
| Roles sin escritura | product, pmo, scrum_master, architecture, reviewer |

Instalación (una vez, en la máquina donde se usa Claude Code):

```text
/plugin marketplace add robertosl77/agent-dev-kit
/plugin install agent-dev-kit@agent-dev-kit
```

Uso, dentro de cualquier repo:

```text
/agent-dev-kit:orquestar <pedido>
```

## claude.ai — skills

17 zips (`adk-triage` + 16 especialistas). Cada zip es un skill; se suben uno por
uno en **Customize → Skills → + → Create skill → Upload a skill**. Requiere
"Code execution and file creation" activado.

En el Proyecto, agregar a las instrucciones:

```text
Para todo pedido de desarrollo usá primero el skill adk-triage y seguí su procedimiento.
```

Diferencia con Claude Code: en claude.ai es un único modelo que ejecuta los nodos
rol por rol; en Claude Code cada especialista es un subagente real.
