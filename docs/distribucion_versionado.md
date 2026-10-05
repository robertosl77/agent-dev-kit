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

Cuando Agent Dev Kit pase a privado, el contrato de versión no cambia.

El entorno que instala la dependencia necesita credenciales Git válidas.

Para HTTPS se recomienda que la autenticación la resuelva el entorno mediante
credential manager, token efímero/CI secret o mecanismo corporativo equivalente.
No se deben incrustar tokens en `pyproject.toml`, URLs versionadas ni
`.agent-dev-kit/project.yaml`.

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

## Smoke del artefacto distribuible

El CI no valida únicamente una instalación editable. El job
`Agent Dev Kit CI / package-smoke`:

1. construye wheel y sdist con `python -m build`;
2. crea un entorno virtual limpio;
3. instala el wheel producido con el extra `mcp`;
4. importa `agent_dev_kit` desde ese entorno;
5. verifica que `profiles/default.yaml` esté incluido como package data;
6. valida el entrypoint `agent-dev-kit`;
7. construye el servidor MCP sin iniciar red ni consumir APIs externas.

Un release no debe publicarse si este smoke falla.

## Checklist de release

Flujo de release con las ramas actuales:

```text
task branches
      ↓
develop
      ↓ CI verde
release PR
develop → main
      ↓ CI verde del PR
merge
      ↓ CI verde de main
tag SemVer
      ↓
GitHub Release
```

Antes de crear un tag:

1. no debe existir una modernización funcional bloqueante abierta;
2. `pyproject.toml` debe contener la versión correcta;
3. toda la suite y el smoke E2E deben pasar en `develop`;
4. README, CHANGELOG y documentación deben reflejar la estructura real;
5. debe abrirse un PR de release `develop → main`;
6. el CI del PR de release debe estar verde;
7. después del merge, el CI del commit final de `main` debe estar verde;
8. el tag debe apuntar exactamente a ese commit final de `main`;
9. el GitHub Release debe usar el mismo número del tag.

No se crea una rama `v0.1.0`: la versión se marca mediante tag.

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
