# Distribución y versionado

## Objetivo

Agent Dev Kit se consume como dependencia.

El proyecto consumidor no copia `src/agent_dev_kit/`.

## Estrategia inicial

La primera etapa de distribución utiliza Git:

```text
proyecto consumidor
        ↓
dependencia Git fijada a versión
        ↓
agent-dev-kit v0.1.0
```

Una publicación futura en un índice de paquetes puede agregarse sin cambiar el
contrato de configuración del consumidor.

## Versionado semántico

Agent Dev Kit utiliza SemVer:

```text
MAJOR.MINOR.PATCH
```

Para la etapa inicial:

- PATCH: corrección compatible;
- MINOR: capacidad nueva compatible;
- MAJOR: cambio incompatible de contrato.

La primera versión utilizable es:

```text
v0.1.0
```

Mientras el major sea cero, el framework sigue en evolución temprana y los
cambios incompatibles deben documentarse explícitamente.

## Instalación desde un tag

Core:

```bash
python -m pip install \
  "agent-dev-kit @ git+https://github.com/robertosl77/agent-dev-kit.git@v0.1.0"
```

Con provider OpenAI:

```bash
python -m pip install \
  "agent-dev-kit[openai] @ git+https://github.com/robertosl77/agent-dev-kit.git@v0.1.0"
```

Con MCP y OpenAI:

```bash
python -m pip install \
  "agent-dev-kit[openai,mcp] @ git+https://github.com/robertosl77/agent-dev-kit.git@v0.1.0"
```

## Declararlo en pyproject.toml del consumidor

Ejemplo:

```toml
dependencies = [
  "agent-dev-kit[openai,mcp] @ git+https://github.com/robertosl77/agent-dev-kit.git@v0.1.0"
]
```

De esta forma una actualización de `main` no modifica inesperadamente el
comportamiento del proyecto consumidor.

## Repositorio privado

Cuando Agent Dev Kit pase a privado, el contrato no cambia.

El entorno que instala la dependencia necesita credenciales Git válidas.

Una alternativa basada en SSH es conceptualmente:

```toml
dependencies = [
  "agent-dev-kit[openai,mcp] @ git+ssh://git@github.com/robertosl77/agent-dev-kit.git@v0.1.0"
]
```

Las credenciales no deben escribirse dentro de `.agent-dev-kit/project.yaml`
ni del repositorio consumidor.

## Pin por commit

Para pruebas anteriores a un release también puede fijarse un commit concreto:

```text
git+https://github.com/robertosl77/agent-dev-kit.git@<commit-sha>
```

Un commit es reproducible, pero para consumo normal se prefieren tags SemVer
porque comunican intención y compatibilidad.

## Integración en Librería Inglés

Librería Inglés mantiene únicamente su configuración:

```text
LibreriaIngles/
└── .agent-dev-kit/
    ├── project.yaml
    ├── preferences.yaml
    └── agents/
        ├── pmo.yaml
        └── ...
```

El código de los agentes proviene de la dependencia versionada.

## Checklist de release

Antes de crear un tag:

1. no debe existir una modernización funcional bloqueante abierta;
2. `pyproject.toml` debe contener la versión correcta;
3. tests y smoke test deben pasar en CI sobre `main`;
4. README y documentación deben reflejar la estructura real;
5. CHANGELOG debe describir la versión;
6. el tag debe apuntar exactamente al commit verde de `main`;
7. el release debe usar el mismo número del tag.

Para `v0.1.0`:

```text
pyproject version = 0.1.0
tag               = v0.1.0
release            = v0.1.0
```

## Regla

Nunca consumir `main` como dependencia estable de un proyecto importante.

El consumidor debe fijar un tag o, excepcionalmente, un commit.


## Distribución cerrada futura

La distribución inicial de v0.1.0 mediante dependencia Git versionada supone que
el consumidor autorizado puede obtener el paquete/código necesario para
instalarlo.

La necesidad distinta de usar Agent Dev Kit sin entregar su implementación fue
analizada en M-027.

Decisión:

- v0.1.0 mantiene la distribución reproducible mediante tag Git;
- la vía cerrada principal futura será un servicio remoto de Agent Dev Kit con
  acceso al repositorio mediante GitHub App y una interfaz cliente basada en
  MCP;
- un paquete privado no debe presentarse como mecanismo fuerte de ocultamiento;
- un artefacto compilado queda como alternativa secundaria para escenarios
  offline/on-premise.

Ver `docs/distribucion_cerrada.md`.
