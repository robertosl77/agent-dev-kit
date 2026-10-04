# Distribución cerrada de Agent Dev Kit

## Estado de la decisión

M-027 define la estrategia de distribución cerrada antes de v0.1.0, pero no implementa todavía esa distribución.

Decisión recomendada:

~~~text
Vía principal corporativa futura
        ↓
Agent Dev Kit Service remoto
        ↓
MCP autenticado
        ↓
GitHub App con acceso mínimo/selectivo
        ↓
Repositorio consumidor
~~~

Como alternativa futura para entornos offline o muy restringidos puede evaluarse un artefacto local compilado, pero no se considera equivalente en protección del código.

## Requisito real

Hay dos necesidades distintas:

1. que el consumidor no tenga acceso al repositorio fuente;
2. que el consumidor no reciba una copia inspeccionable de la implementación.

Una distribución privada de paquetes satisface principalmente la primera. Un servicio remoto satisface ambas de forma mucho más fuerte.

## Opción A — Paquete privado

Ejemplos: índice Python privado, registry interno o distribución de wheels por canal autenticado.

### Encaje con Agent Dev Kit

Es la alternativa más cercana al modelo actual de instalación con pip y respeta bien pyproject.toml, extras, CLI y configuración .agent-dev-kit/.

### Ventajas

- instalación simple y familiar;
- SemVer, pinning y rollback sencillos;
- muy poca infraestructura adicional;
- mantiene ejecución local;
- funciona bien con CLI y MCP local.

### Desventajas

- no cumple de forma fuerte el requisito de ocultar la implementación;
- un wheel es un archivo instalable/desempaquetable;
- un paquete Python puro distribuye material directamente inspeccionable por el consumidor;
- las credenciales del registry controlan quién descarga, no qué puede inspeccionar quien ya descargó.

### Evaluación

**No se recomienda como solución principal de distribución cerrada.**

Sí puede existir en el futuro como canal privado de distribución para consumidores de confianza, pero no debe presentarse como protección del código fuente.

## Opción B — GitHub App + servicio remoto

Agent Dev Kit se ejecuta fuera del repositorio consumidor.

~~~text
cliente / Copilot / otro host
        ↓ MCP/API
Agent Dev Kit Service
        ↓
Gateway
        ↓
Orquestador
        ↓
GitHub App
        ↓
repositorio autorizado
~~~

### Autenticación y acceso

GitHub Apps permiten seleccionar los repositorios a los que la instalación tiene acceso. Los installation access tokens pueden emitirse con permisos y repositorios reducidos respecto de lo concedido a la instalación y expiran aproximadamente a la hora.

En organizaciones con SAML/SSO puede haber requisitos adicionales de sesión y aprobación para instalar o autorizar la aplicación.

### Permisos mínimos propuestos

El diseño debe partir de deny-by-default y ampliar sólo por capability habilitada.

Perfil base de sólo lectura:

- metadata: read;
- contents: read;
- pull requests: read;
- issues: read.

Permisos de escritura opcionales y separados:

- issues: write, sólo si el proyecto permite crear/actualizar Issues;
- pull requests: write, sólo si el workflow permite crear/actualizar PRs;
- contents: write, sólo si Agent Dev Kit está autorizado a crear commits/ramas;
- workflows/actions: únicamente si una capacidad concreta lo necesita.

Los permisos finales deben derivarse de herramientas habilitadas por proyecto, no de un conjunto fijo sobredimensionado.

### Aislamiento

Cada instalación/consumidor debe tener aislamiento lógico y de credenciales:

- installation_id propio;
- token temporal propio;
- configuración de proyecto separada;
- storage/telemetría separada;
- namespace de cache separado;
- logs sin secretos;
- prohibición de reutilizar contexto entre consumidores.

### Ejecución

Para el objetivo de ocultar el código, la modalidad recomendada es servicio remoto. Un webhook puede disparar trabajo, pero no es requisito para todas las operaciones: MCP/API también puede iniciar tareas interactivas.

### Updates y rollback

El servicio despliega una versión concreta de Agent Dev Kit asociada a un tag SemVer. Cada despliegue registra la versión. Rollback significa volver a desplegar una versión anterior validada.

### Ventajas

- el consumidor no recibe el código de Agent Dev Kit;
- actualizaciones centralizadas;
- control de versión y rollback del servicio;
- permisos GitHub granulares;
- buena base para consumidores múltiples;
- encaja con Gateway y MCP existentes.

### Desventajas

- infraestructura y operación adicionales;
- autenticación remota, tenancy, observabilidad y backups;
- dependencia de red;
- requisitos corporativos de aprobación, data residency y seguridad;
- costo operativo.

### Evaluación

**Es la vía principal recomendada para distribución cerrada corporativa.**

## Opción C — Ejecutable/artefacto compilado

Ejemplos: PyInstaller, compilación parcial con Cython/Nuitka, contenedor o artefacto equivalente.

### Ventajas

- ejecución local;
- puede funcionar offline;
- distribución más simple que un SaaS completo;
- evita entregar directamente el repositorio fuente;
- conserva CLI y potencialmente MCP local.

### Límites reales

PyInstaller agrupa la aplicación y sus dependencias, pero los módulos Python empaquetados se basan en bytecode/archivos embebidos que pueden ser objeto de extracción o ingeniería inversa. No debe considerarse una frontera de confidencialidad equivalente a un servicio remoto.

Además, PyInstaller no es cross-compiler: se construye por plataforma objetivo. Esto multiplica pipelines y artefactos para Windows, macOS y Linux.

Un contenedor tampoco evita por sí mismo que quien recibe la imagen inspeccione su filesystem/capas.

### Evaluación

**Alternativa secundaria**, útil para offline/on-premise controlado, no como garantía fuerte de ocultamiento.

## Opción D — Estrategia combinada

~~~text
Corporate/connected
→ servicio remoto + GitHub App + MCP

Offline/on-premise excepcional
→ artefacto local compilado/firmado
~~~

### Ventajas

- cubre organizaciones conectadas y entornos restringidos;
- mantiene un contrato de configuración común;
- permite evolucionar el servicio sin abandonar casos offline.

### Desventajas

- dos modelos operativos;
- más testing de releases;
- soporte multiplataforma adicional;
- garantías de protección distintas según modalidad.

### Evaluación

**Objetivo de largo plazo razonable**, pero no conviene implementar ambas vías a la vez al comenzar.

## Matriz resumida

| Criterio | Paquete privado | Servicio + GitHub App | Compilado local | Combinada |
| --- | --- | --- | --- | --- |
| Oculta repo fuente | Sí | Sí | Sí | Sí |
| Evita entregar implementación | No | Sí | Parcial | Según modo |
| Ejecución offline | Sí | No | Sí | Sí |
| Infraestructura propia | Baja | Alta | Media | Alta |
| Updates centralizados | Medio | Alto | Medio | Alto |
| Multiplataforma | Alto en pure Python | Cliente ligero | Build por plataforma | Mixto |
| Encaje MCP | Alto local | Alto remoto | Alto local | Alto |
| Encaje corporativo | Medio | Alto, sujeto a aprobación | Medio/alto | Alto |

## Relación con M-029

M-029 define MCP como interfaz base para Copilot. Esto encaja directamente con el servicio remoto:

~~~text
Copilot / otro cliente
        ↓
MCP autenticado
        ↓
Agent Dev Kit Service
        ↓
GitHub App
        ↓
repositorio
~~~

GitHub App controla acceso al repositorio. MCP controla la interacción cliente → Agent Dev Kit. Son responsabilidades distintas.

## Contratos que deben mantenerse

La distribución remota no debe cambiar conceptos públicos innecesariamente:

- Project config sigue siendo .agent-dev-kit/project.yaml;
- Gateway sigue siendo la frontera del proyecto;
- orchestration.py sigue siendo dueño de gates y trazas;
- task_plan.py sigue definiendo el DAG;
- GitPolicyGuard sigue validando mutaciones;
- CLI/MCP son clientes/adaptadores, no dueños del dominio;
- providers internos siguen separados de clientes externos.

## Secretos

Principios:

- nunca persistir credenciales en project.yaml;
- usar secret store del entorno de ejecución;
- installation tokens temporales;
- rotación/revocación;
- no escribir secretos en traces;
- separar credenciales por consumidor;
- minimizar scope de tokens.

## Alcance de v0.1.0

v0.1.0 NO implementa distribución cerrada.

Sí deja decidido y documentado:

- servicio remoto + GitHub App como vía principal futura;
- MCP como interfaz remota natural;
- paquete privado no equivale a ocultar código;
- artefacto compilado como alternativa secundaria/offline;
- estrategia combinada como evolución posterior.

La distribución inicial de v0.1.0 continúa siendo la definida por M-011 mediante tag Git reproducible.

## Roadmap

### v0.2.x — prototipo remoto

- definir contrato de servicio alrededor de Gateway;
- autenticación del cliente MCP;
- GitHub App de laboratorio;
- installation tokens por repo;
- permissions matrix;
- tenant isolation;
- storage de configuración/trace por consumidor;
- prueba end-to-end contra repositorio sandbox.

### v0.2.x / v0.3.x — hardening corporativo

- SSO/approval flows;
- audit log;
- rate limits;
- backups/disaster recovery;
- data retention/residency;
- observabilidad y SLO;
- despliegue versionado/rollback;
- modelo de costos.

### v0.3.x+ — offline/on-premise opcional

- evaluar artefacto compilado;
- firma/verificación;
- builds Windows/macOS/Linux;
- política de actualización;
- documentar claramente el menor nivel de protección frente al servicio remoto.

## Referencias externas

- Python wheel format: https://packaging.python.org/en/latest/specifications/binary-distribution-format/
- Python package formats: https://packaging.python.org/en/latest/discussions/package-formats/
- PyInstaller manual: https://pyinstaller.org/en/stable/
- GitHub App installation: https://docs.github.com/en/apps/using-github-apps/installing-a-github-app-from-a-third-party
- GitHub App installation tokens: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation
- SAML and GitHub Apps: https://docs.github.com/en/enterprise-cloud@latest/apps/using-github-apps/saml-and-github-apps
