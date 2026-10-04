# Política Git por proyecto

## Objetivo

Agent Dev Kit debe conocer y hacer cumplir el workflow Git del proyecto
consumidor.

La política no depende únicamente de instrucciones al modelo. Existe una capa
determinística, `GitPolicyGuard`, que valida operaciones sensibles antes de
ejecutarlas.

## Workflow recomendado de dos ramas largas

```text
main
↑ producción / releases

development
↑ integración del siguiente ciclo

feat/t-123-corregir-reporte
↑ rama exclusiva de una tarea
```

QA puede ser una etapa o entorno. No se exige una tercera rama permanente.

## Configuración

En `.agent-dev-kit/project.yaml`:

```yaml
git_workflow:
  branches:
    production: main
    integration: development

  protected:
    - main
    - development

  task_branch:
    base: development
    naming: "{kind}/{issue}-{slug}"

  pull_requests:
    task_target: development
    release_source: development
    release_target: main
    require_issue_reference: true

  sync:
    require_updated_base_before_task: true

  direct_writes:
    protected_branches: deny
    exception: explicit_human_authorization
```

## Flujo de una tarea

```text
Issue
  ↓
sincronizar development
  ↓
crear rama de tarea desde development
  ↓
trabajo multiagente
  ↓
Testing
  ↓
Reviewer
  ↓
Documentation
  ↓
QA humano
  ↓
PR rama tarea → development
```

Una rama de tarea creada desde `main` debe ser rechazada.

## Flujo de release

```text
development
      ↓
release PR
      ↓
main
      ↓
CI / QA acordado
      ↓
tag + GitHub Release
```

Un PR de tarea normal no puede apuntar directamente a `main`.

## Protección

`main` y `development` son ramas protegidas por la política lógica.

Por defecto:

- no se permite escritura directa;
- no se permite usarlas como rama de tarea;
- una excepción requiere autorización humana explícita;
- un agente no puede autoautorizarse.

Ejemplo de rechazo:

```text
GitPolicyViolation:
Direct write to protected branch 'main' is forbidden.
```

## GitPolicyGuard

La capa de integración Git debe invocar el guard antes de una mutación.

Valida:

- escritura directa;
- rama base de una tarea;
- referencia a Issue;
- base actualizada;
- target de PR de tarea;
- source/target de PR de release.

Ejemplo:

```python
guard.validate_task_branch_creation(
    "feat/t-123-report",
    base_branch="development",
    issue_reference="T-123",
    base_is_updated=True,
)
```

## Defensa en profundidad

La política del framework no reemplaza la protección real del proveedor Git.

Para GitHub se recomienda proteger también `main` y `development` mediante
Rulesets o Branch Protection.

Así existen dos barreras:

```text
Agent Dev Kit GitPolicy
          +
GitHub Rulesets / Branch Protection
          =
defensa en profundidad
```

## Responsabilidades

### PMO

Antes de recomendar ejecución debe conocer:

- Issue;
- rama base;
- rama de tarea;
- target del PR;
- bloqueos.

### Reviewer

Antes de considerar técnicamente completa una entrega debe comprobar:

- que la rama nació del lugar correcto;
- que el PR tiene el target correcto;
- que no hubo una escritura protegida no autorizada.

### Integraciones Git

Nunca deben exponer mutaciones a los agentes saltando `GitPolicyGuard`.

## Regla

La configuración concreta pertenece al consumidor.

Agent Dev Kit define el mecanismo de enforcement; cada proyecto define los
nombres de sus ramas y su workflow.


## Enforcement de mutaciones Git

Las integraciones Git soportadas no deben invocar escrituras externas
directamente. Deben pasar por `GitMutationGateway`, que valida primero con
`GitPolicyGuard` y sólo después ejecuta la operación externa.

```text
agente / tool
    ↓
GitMutationGateway
    ↓
GitPolicyGuard
    ↓
executor Git/GitHub
    ↓
Ruleset del proveedor
```

Para herramientas registradas mediante `ToolRegistry`, las mutaciones Git
deben usar `register_git_mutation(...)`. Esa vía construye el tool nativo
alrededor del gateway guardado y deja metadata `effect=git_mutation` y
`enforced_policy=git_policy_guard`.

Las herramientas externas genéricas registradas con `register(...)` son
extensiones opacas de confianza. El framework no puede inspeccionar una callback
arbitraria y descubrir si internamente hace escrituras Git; una integración que
oculte efectos laterales fuera de la vía soportada queda fuera de la garantía.

## Override humano verificable

El booleano `human_override=True` dejó de ser válido.

Una excepción requiere un `HumanAuthorization` con:

- token opaco;
- actor humano;
- scope exacto de la acción;
- razón opcional.

Además, `GitPolicyGuard` requiere un `authorization_verifier` externo. Sin
verificador, incluso un objeto `HumanAuthorization` bien formado es rechazado.

Los scopes son específicos, por ejemplo:

```text
git:direct_write:main
git:create_task_branch:feat/m-031-enforcement
git:create_pull_request:release:development->main
```

Esto evita que un agente se autoautorice pasando un simple flag y evita reutilizar
una aprobación para una acción distinta.
