# Activación de agentes por proyecto consumidor

## Objetivo

Un proyecto consumidor no tiene por qué utilizar todos los agentes disponibles en Agent Dev Kit.

La configuración `agents.enabled` define cuáles existen efectivamente en runtime.

## Ejemplo

```yaml
agents:
  enabled:
    - pmo
    - architecture
    - backend
    - frontend
    - testing
    - reviewer
    - triage
```

En ese proyecto:

- esos agentes pueden instanciarse;
- Triage puede derivar únicamente hacia esos especialistas;
- los agentes que no aparecen en la lista no se instancian;
- una configuración contextual de un agente deshabilitado permanece inactiva.

## Regla de seguridad funcional

La lista es explícita y restrictiva.

```text
No está en agents.enabled
        ↓
no se instancia
        ↓
Triage no lo conoce
        ↓
no puede recibir un handoff accidental
```

Esto permite que un proyecto utilice solo el subconjunto de responsabilidades que decidió habilitar.

## Ejemplo: Librería Inglés

```yaml
agents:
  enabled:
    - pmo
    - architecture
    - ux_ui
    - backend
    - frontend
    - database
    - security
    - testing
    - reviewer
    - documentation
```

Si `data`, `observability` o `devops` no están habilitados, el runtime no debe crearlos aunque sus archivos existan dentro del paquete.

## Triage

Triage también es optativo.

Si está habilitado, se crea después de los demás y recibe como handoffs únicamente los agentes habilitados del proyecto.

Si Triage no está habilitado, los especialistas pueden utilizarse de forma directa.

## Claves inválidas

Una clave desconocida debe fallar de forma explícita.

Ejemplo incorrecto:

```yaml
agents:
  enabled:
    - backend
    - super_agent
```

El framework no debe ignorar silenciosamente `super_agent`. Debe informar el error de configuración.

## Configuración contextual

La activación y la configuración contextual son conceptos independientes.

Puede existir:

```text
.agent-dev-kit/agents/data.yaml
```

pero si `data` no figura en `agents.enabled`, esa configuración no activa al agente por sí sola.

## Principio

> El framework contiene el catálogo completo; cada proyecto consumidor decide qué subconjunto está activo.
