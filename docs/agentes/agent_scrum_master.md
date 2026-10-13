# Agent Scrum Master

## Rol

Combina facilitación Scrum y funciones **operativas** de Product Owner. Su primer resultado es una historia de usuario verificable que permita al usuario confirmar si Agent Dev Kit entendió el pedido **antes de implementar**.

## Activación

En `.agent-dev-kit/project.yaml`:

```yaml
agents:
  enabled:
    - triage
    - scrum_master
    - frontend
    - testing
```

No se activa automáticamente en proyectos que aún no lo habilitaron.

## Comportamiento proporcional

- Nueva capacidad o cambio funcional: una o pocas historias, criterios de aceptación y pregunta de confirmación, incluso para un campo del formulario.
- Iniciativa amplia: historias priorizadas, roadmap incremental, Sprint Goal, Sprint Backlog, Increment y Definition of Done, si corresponden.
- Bug técnico localizado o incidente sin decisión funcional: no agrega ceremonias ni participa salvo pedido expreso.

### Ejemplo

Pedido: «Agregar al formulario la opción de cambiar la moneda».

**HU-001**: Como usuario quiero seleccionar la moneda de los importes para visualizar los valores en la unidad deseada.

**Criterios de aceptación a confirmar**:
1. El formulario tiene un selector visible de moneda.
2. Permite elegir entre monedas que el usuario defina.
3. La selección se refleja en el formulario.

**Duda:** ¿solo cambia el símbolo o hay conversión de valores? No asumir tasas, monedas soportadas ni persistencia.

## Barrera humana

La planificación ubica a Scrum Master como **único nodo raíz** y obliga a que los otros agentes dependan de su salida. En `/task` y `/do`, la historia se muestra y exige respuesta:

- **Sí:** se permite continuar con los nodos técnicos.
- **No:** se detiene la ejecución. Se puede reformular el pedido; no se produce una aprobación ficticia.

En `/do`, esta lectura se realiza antes de crear una rama, con herramientas de **solo lectura**. El runtime de Python también exige `story_approved=True` después del intake; no basta con llamar directamente a `execute_plan_sync`.

`/plan` solo muestra el DAG y no ejecuta agentes.

## Límites de responsabilidad

- **Product:** discovery, visión, PRD y definición estratégica.
- **Scrum Master:** historias, criterios y marco Scrum proporcional.
- **PMO:** administración de issues, dependencias y seguimiento de entregas.
- **Testing:** automatización de pruebas y evidencia técnica.
- **Agentes técnicos:** implementación y decisiones técnicas.
- **Usuario:** autoridad final sobre alcance y aceptación funcional.

## GitHub

El agente puede **proponer** títulos y contenidos de GitHub Issues y cómo enlazarlos a las historias; no crea ni modifica issues sin autorización explícita y una integración con permisos. La herramienta integrada `read_issue` es de solo lectura. La escritura de issues es una capacidad posterior, separada de esta primera incorporación.
