# Modos de consola: /plan, /task y /do

Desde `v0.3.0` los agentes tienen **herramientas** (M-076): pueden leer el proyecto, leer issues de GitHub y, en modo acción, cambiar archivos y correr tests en una rama local.

```text
/plan <pedido>   solo el plan: qué agentes, en qué orden y con qué modelo. No ejecuta nada.
/task <pedido>   plan + propuesta de cada agente. Leen el repo; no lo modifican.
/do   <pedido>   plan → tu OK → rama local desde develop → cambian archivos y corren tests
                 → diff y consumo → tu OK → commit local. Nunca hace push.
/help            ayuda
/exit            salir
```

Cualquier otro texto es una conversación; los agentes también pueden leer el repo para responder.

Sin entrar a la sesión:

```bash
agent-dev-kit task . "pedido" --mode plan      # solo plan
agent-dev-kit task . "pedido"                  # propuesta (default)
agent-dev-kit task . "T-066 pedido" --mode act # acción
```

## Herramientas

| Herramienta | Modo | Qué hace |
|---|---|---|
| `list_files` | todos | lista archivos (omite `.git`, `node_modules`, entornos virtuales y secretos) |
| `read_file` | todos | lee un archivo con números de línea, por tramos |
| `search` | todos | busca una expresión regular en el proyecto |
| `git_status` / `git_log` / `git_diff` | todos | estado, historial (con fecha y autor) y cambios (solo lectura) |
| `git_branches` | todos | ramas locales y de `origin` según el último `git fetch` (no consulta GitHub en vivo); sirve para verificar nombres de ramas |
| `read_issue` | todos | lee una issue de GitHub del proyecto (título, cuerpo y comentarios) |
| `write_file` / `replace_in_file` | `/do` | crea o modifica archivos |
| `run_command` | `/do` | corre comandos declarados por el proyecto |

Reglas que aplica el framework, no el modelo:

- todo path queda dentro del proyecto; `..` o rutas absolutas afuera se rechazan;
- `.git/` no se lee ni se escribe; `.agent-dev-kit/` no se escribe;
- `.env` y `.env.*` (salvo `.env.example`) no se leen ni se escriben;
- git en las herramientas es solo lectura. La rama y el commit de `/do` pasan por `GitPolicyGuard`.

### Quién puede escribir en `/do`

Por defecto escriben: backend, frontend, database, testing, documentation, devops, ux_ui, data, performance, observability y security. Solo leen: product, pmo, architecture, reviewer y triage.

Se cambia por agente en `.agent-dev-kit/agents/<agente>.yaml`:

```yaml
agent: security
access: read_only      # o read_write
```

### Qué resuelve el framework y qué el modelo (M-084, M-085)

Lo que se puede verificar con código no se le pide al modelo:

```text
/task o /do
  0. rama actual ≠ develop → aviso y pregunta (en /task; /do ya parte de develop)   ← sin tokens
  1. Triage planifica (motivos ≤ 12 palabras)
  2. hoja de hechos (código):                                                       ← sin tokens
       rama actual · ramas conocidas · fuentes de reglas (context.rule_sources)
       issue ya leída · criterios CA-1…n (los que refieren a reglas, marcados)
       ramas escritas en los archivos citados que no existen en git
  3. el agente trabaja con el pedido + hechos + plan real (sin herramientas transfer_to_*)
  4. control del veredicto (código):                                                ← sin tokens
       [OK] CA-n | path:línea | "texto exacto"
       cita inexistente / texto que no está en esa línea / OK sin cita /
       criterio de reglas que no cita la fuente   →  [PENDIENTE] + motivo
       criterio no evaluado                       →  se agrega [PENDIENTE]
```

- El control solo baja de `OK` a `PENDIENTE`; nunca sube.
- El plan real de Triage llega al nodo para informarlo tal cual (se omite si no
  cabe en el presupuesto). Los hechos tienen prioridad sobre el plan; un nodo sin
  dependencias no reserva espacio para evidencia que no tiene.
- El nodo final sabe que su salida va directo a la persona: formato pedido, sin
  preámbulo, nada fuera del pedido salvo una línea de hallazgos colaterales.
- Si el pedido apunta a una fuente que contradice los hechos o las fuentes de
  reglas, manda la fuente y el agente señala la contradicción.

## Flujo de /do y aprobaciones

```text
/do T-066 corregir el README
  0. controles sin costo: repo limpio, issue de la tarea, develop existe y está igual que origin/develop
  1. Triage arma el plan → se muestran agentes, nodos, modelo y consumo de la planificación
     [OK 1] ¿Ejecutar este plan?            ← el punto barato para frenar
  2. rama local  <kind>/<issue>-<slug>  desde develop  (vía GitMutationGateway)
  3. los agentes leen, cambian archivos y corren comandos:
       - workspace.test_commands     → corren sin preguntar
       - workspace.allowed_commands  → [OK] ¿Ejecutar el comando …?
       - cualquier otro              → rechazado
  4. resumen: rama, archivos cambiados, comandos y consumo
     [OK 4] ¿Commitear estos cambios en la rama local?
  5. commit local. Sin push: lo subís vos cuando decidas.
```

Si respondés que no en el paso 4, los cambios quedan en la rama sin commitear para revisarlos. Las confirmaciones son locales y no consumen tokens.

Si el pedido no menciona una issue (`T-066`, `M-012` o `#96`) y la política la exige, se pregunta antes de planificar.

## Configuración en `project.yaml`

```yaml
project:
  name: LibreriaIngles
  language: es              # idioma de las respuestas (M-077)

workspace:
  test_commands:            # corren sin preguntar
    - pytest -q
    - npm test
  allowed_commands:         # preguntan antes de correr
    - alembic upgrade head
  max_read_bytes: 60000     # tope por lectura (cuida el consumo)
  max_search_results: 50
  command_timeout_seconds: 600

context:
  rule_sources:             # documento del repo que manda en cada tema (M-085)
    git_workflow: "docs/tareas_pendientes_v0_1.md#4. Regla de ramas a partir de ahora"

pricing:                    # opcional: para mostrar el costo estimado
  claude-haiku-4-5: {input_per_mtok: 1.0, output_per_mtok: 5.0}
```

Los comandos se ejecutan en la consola desde la que se corre `agent-dev-kit`. Con el entorno virtual activado, `pytest` es el del proyecto.

Los precios no vienen incluidos en agent-dev-kit para no mantener una lista que se desactualiza: si no se declaran, se muestran solo los tokens.

## Issues de GitHub

`read_issue` usa el remoto `origin` del proyecto:

- repo público con cupo disponible → sin token (límite de GitHub: 60 consultas por hora);
- repo privado o cupo agotado → pide un token de GitHub de **solo lectura**, oculto, que no se guarda.

## Consumo y log de grafos

Al terminar cada `/plan`, `/task`, `/do` o respuesta se muestra el consumo:

```text
consumo: planner 9.800 in / 1.900 out · doc-1 3.100 in / 1.200 out · total 12.900 in / 3.100 out ≈ USD 0,0284 (claude-haiku-4-5)
```

Cada uso queda registrado en `.agent-dev-kit/runtime/orchestration-traces.jsonl`: grafo, decisiones de Triage, modo, proveedor, modelo, tokens por etapa y herramientas usadas (sin contenido). Para analizarlo:

```bash
agent-dev-kit graphs .       # lista de usos: modo, estado, agentes, nodos, tokens, modelo
agent-dev-kit candidates .   # resumen y candidatos de mejora de routing (revisión humana)
```

Los registros de `runtime/` nunca entran en el commit de `/do`.

## MCP y API Python

En modo MCP no hay herramientas incluidas: el host (por ejemplo Copilot) usa las suyas. Desde Python se activan pasando `workspace` y `mode` a `ProviderRuntime`.
