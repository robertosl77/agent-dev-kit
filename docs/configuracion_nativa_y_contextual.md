# Configuración nativa y contextual — Agent Dev Kit

## Objetivo

Definir cómo se combinan dos niveles de configuración:

1. **Configuración nativa del framework**: vive en `agent-dev-kit` y define el comportamiento base reusable de cada agente.
2. **Configuración contextual del proyecto consumidor**: vive en cada aplicación que consume el framework y agrega reglas, convenciones y contexto propios de ese proyecto.

La idea central es que **Agent Dev Kit no se copie dentro del proyecto consumidor**.

El consumidor instala o referencia el paquete y mantiene únicamente su configuración local.

---

## 1. Configuración nativa

La configuración nativa pertenece al repositorio:

```text
agent-dev-kit
```

Ejemplo:

```text
agent-dev-kit/
└── src/
    └── agent_dev_kit/
        └── agents/
            └── agent_pmo.py
```

`agent_pmo.py` define el comportamiento general que debería aplicar Agent PMO en cualquier proyecto.

Ejemplos de reglas nativas:

- administrar backlog;
- detectar dependencias y bloqueos;
- recomendar la siguiente tarea ejecutable;
- revisar si una tarea está suficientemente definida;
- mantener trazabilidad entre Issue, rama y PR;
- no asumir decisiones de arquitectura;
- no reemplazar el QA funcional humano.

Una modificación realizada aquí afecta al comportamiento base del agente para todos los proyectos que adopten esa versión del framework.

### Ejemplo

Si se decide:

> Todo Agent PMO debe revisar siempre si una tarea tiene dependencias antes de recomendar su ejecución.

Eso corresponde al repositorio `agent-dev-kit`, porque es una responsabilidad general del rol.

---

## 2. Configuración contextual

La configuración contextual pertenece al **repositorio consumidor**.

Ejemplo:

```text
LibreriaIngles/
├── .agent-dev-kit/
│   ├── project.yaml
│   └── agents/
│       ├── pmo.yaml
│       ├── architecture.yaml
│       └── ux_ui.yaml
├── backend/
├── frontend/
└── docs/
```

Estos archivos no duplican los agentes del framework.

Solo agregan información propia del proyecto.

---

## 3. Ejemplo de configuración general del proyecto

Archivo:

```text
.agent-dev-kit/project.yaml
```

Ejemplo:

```yaml
project:
  name: LibreriaIngles

stack:
  backend:
    language: Python
    framework: FastAPI
  frontend:
    framework: Angular
  ui:
    framework: Bootstrap
  database:
    engine: SQLite

provider:
  name: openai

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

La configuración concreta podrá evolucionar cuando se implemente M-010. Este ejemplo documenta la intención funcional.

---

## 4. Ejemplo contextual de Agent PMO

Archivo:

```text
.agent-dev-kit/agents/pmo.yaml
```

Ejemplo:

```yaml
agent: pmo

extra_instructions:
  - "Usar T-xxx para tareas legacy existentes."
  - "Usar M-xxx para modernizaciones."
  - "QA funcional final lo realiza Roberto."
  - "No cerrar una tarea mientras falte la validación funcional requerida."
  - "Cada tarea debe trabajar en su propia rama, salvo una excepción explícita."
  - "No trabajar directamente sobre main sin autorización explícita."

project_rules:
  backlog_source: github_issues
  workflow: scrum_light
  final_qa: human
```

Estas reglas solo afectan a Agent PMO cuando trabaja sobre Librería Inglés.

No modifican el comportamiento base del PMO para otros proyectos.

---

## 5. Ejemplo contextual de Agent Architecture

Archivo:

```text
.agent-dev-kit/agents/architecture.yaml
```

Ejemplo:

```yaml
agent: architecture

extra_instructions:
  - "Revisar impacto transversal antes de proponer cambios."
  - "Evitar duplicar responsabilidades entre módulos."
  - "Antes de crear una nueva capa, revisar si una existente ya resuelve la responsabilidad."

project_rules:
  preserve_existing_domain_boundaries: true
```

---

## 6. Ejemplo contextual de Agent UX/UI

Archivo:

```text
.agent-dev-kit/agents/ux_ui.yaml
```

Ejemplo:

```yaml
agent: ux_ui

extra_instructions:
  - "Reutilizar componentes existentes antes de crear uno nuevo."
  - "Aplicar el sistema de diseño del proyecto."
  - "Mantener consistencia entre pantallas."

ui:
  framework: Bootstrap
  design_system_source: docs/design-system
```

Agent UX/UI sabe de forma nativa cómo trabajar con sistemas de diseño.

Pero los componentes concretos pertenecen al proyecto consumidor.

Ejemplo:

```text
Agent Dev Kit
└── Agent UX/UI
    └── sabe interpretar y mantener un sistema de diseño

LibreriaIngles
├── Bootstrap
├── tokens visuales
├── botones
├── collapse
├── cards
└── reglas propias
```

Otro proyecto podría utilizar React/Tailwind y tener componentes completamente distintos.

---

## 7. Cómo se forma el agente efectivo

Conceptualmente:

```text
instrucciones nativas del agente
            +
configuración contextual del proyecto
            =
agente efectivo dentro del proyecto consumidor
```

Ejemplo para PMO:

```text
Agent PMO nativo
  ├── administra backlog
  ├── detecta bloqueos
  ├── prioriza
  └── recomienda siguiente trabajo

        +

LibreriaIngles/.agent-dev-kit/agents/pmo.yaml
  ├── usa T-xxx para tareas legacy
  ├── usa M-xxx para modernizaciones
  ├── QA final es humano
  └── reglas específicas de ramas

        =

Agent PMO efectivo de Librería Inglés
```

---

## 8. Qué se modifica y dónde

### Cambio general

Pregunta:

> Quiero que Agent PMO haga esto en todos mis proyectos.

Entonces se modifica:

```text
agent-dev-kit
```

La modificación forma parte del framework y debe versionarse.

### Cambio específico

Pregunta:

> Quiero que Agent PMO haga esto solamente en Librería Inglés.

Entonces se modifica:

```text
LibreriaIngles/.agent-dev-kit/
```

No se toca el framework.

---

## 9. No duplicar Agent Dev Kit en el consumidor

El proyecto consumidor **no debería contener una copia de**:

```text
agent_pmo.py
agent_architecture.py
agent_backend.py
...
```

Esos archivos pertenecen al paquete reutilizable.

El consumidor mantiene solo:

- configuración;
- reglas propias;
- documentación local;
- componentes;
- decisiones;
- stack;
- datos específicos del proyecto.

Esto evita forks accidentales y permite actualizar Agent Dev Kit de forma controlada.

---

## 10. Versionado

Cuando Agent Dev Kit tenga versiones estables, un proyecto consumidor debería indicar qué versión utiliza.

Conceptualmente:

```text
LibreriaIngles
└── Agent Dev Kit v0.3.0
```

Si luego Agent PMO cambia globalmente en `v0.4.0`, Librería Inglés puede decidir cuándo actualizar.

Esto evita que una modificación del framework cambie inesperadamente el comportamiento de un proyecto consumidor.

---

## 11. Relación con proveedores

La configuración contextual es independiente del proveedor.

Ejemplo:

```yaml
provider:
  name: openai
```

En otro contexto podría ser otro adaptador:

```yaml
provider:
  name: copilot
```

Los agentes y sus reglas contextuales no deberían tener que reescribirse por cambiar el proveedor.

---

## 12. Regla conceptual

La separación puede resumirse así:

> **Agent Dev Kit define quién es el agente. El proyecto consumidor define dónde está trabajando, con qué tecnologías y bajo qué reglas locales.**

Esta separación permite reutilizar los mismos agentes entre aplicaciones sin perder la capacidad de adaptarlos profundamente a cada proyecto.
