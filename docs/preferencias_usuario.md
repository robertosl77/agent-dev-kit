# Preferencias persistentes del usuario

## Objetivo

Agent Dev Kit puede conservar criterios de trabajo que el usuario aplica repetidamente entre proyectos.

En este framework las preferencias globales pertenecen al propio repositorio Agent Dev Kit.

## Jerarquía

```text
reglas nativas del framework
          ↓
preferencias globales del usuario
          ↓
preferencias/overrides del proyecto
          ↓
instrucción concreta de la tarea
```

La capa más específica puede especializar o desactivar una preferencia general.

## Perfil global

El perfil global se distribuye con Agent Dev Kit:

```text
src/agent_dev_kit/profiles/default.yaml
```

Ejemplo:

```yaml
preferences:
  - id: modular_structure
    rule: "Preferir módulos cohesivos frente a componentes monolíticos."
    agents:
      - architecture
      - backend
      - frontend
```

Estas preferencias se aplican automáticamente a los agentes cuyo alcance coincide.

## Preferencias por proyecto

Un consumidor puede crear:

```text
.agent-dev-kit/preferences.yaml
```

### Desactivar una global solo en este proyecto

```yaml
disabled_global:
  - modular_structure
```

### Agregar una preferencia exclusiva del proyecto

```yaml
preferences:
  - id: legacy_single_file
    rule: "En este módulo legacy no dividir archivos hasta terminar la migración."
    agents:
      - backend
```

Esto permite mantener una preferencia global sin convertirla en una ley absoluta.

## Exclusiones desde el perfil global

Una preferencia global también puede excluir proyectos explícitamente:

```yaml
- id: modular_structure
  rule: "Preferir módulos cohesivos."
  agents:
    - architecture
    - backend
  exclude_projects:
    - PrototypeProject
```

## Aprendizaje y confirmación

Una corrección aislada nunca se convierte automáticamente en una preferencia permanente.

El flujo es:

```text
observación
    ↓
otra observación compatible
    ↓
patrón repetido
    ↓
preferencia candidata
    ↓
confirmación humana
    ↓
preferencia global persistente
```

El framework mantiene:

- cantidad de observaciones;
- proyectos donde apareció;
- agentes relacionados;
- regla candidata.

Una candidata puede considerarse lista para preguntar después de un umbral, pero sigue sin aplicarse hasta que el usuario la confirma.

## Ejemplo

Después de varias correcciones similares:

> Se detectó un patrón: preferís modularizar cuando un archivo concentra responsabilidades distintas. ¿Querés convertirlo en preferencia global?

Si el usuario confirma, la regla pasa al perfil global.

Si responde que aplica solo a un proyecto, debe registrarse en la configuración contextual de ese proyecto.

Si responde que no aplica a un proyecto concreto, ese proyecto puede desactivarla.

## Principio

El sistema puede **detectar y proponer** patrones; no debe convertir inferencias circunstanciales en reglas permanentes sin confirmación.
