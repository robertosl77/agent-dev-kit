# Ejecución, proveedores y fallback

## Ejecutar Agent Dev Kit

Una vez instalado desde un proyecto consumidor:

```bash
agent-dev-kit run .
```

El comando:

1. busca `.agent-dev-kit/project.yaml`;
2. carga stack, agentes, preferencias y proveedor;
3. crea únicamente los agentes habilitados;
4. abre una conversación;
5. utiliza Triage como punto inicial cuando está habilitado.

### Un solo mensaje

```bash
agent-dev-kit run . --once "Revisá el módulo de membresías"
```

### Tarea multi-especialista

```bash
agent-dev-kit task . "El reporte tiene datos incorrectos y la pantalla necesita rediseño"
```

El comando `task` solicita a Triage un DAG, valida agentes requeridos y ejecuta los nodos respetando dependencias.

## Configuración de proveedor

Configuración simple:

```yaml
provider:
  name: openai
```

Con fallback:

```yaml
provider:
  name: gemini
  default_model: model-primary
  fallback_policy: ask
  fallbacks:
    - name: openai
      default_model: model-backup
    - name: claude
      default_model: another-backup
```

Esta configuración **no instala adaptadores**.

Solo puede utilizarse un proveedor que esté registrado en `ProviderRegistry`. Agent Dev Kit incluye inicialmente el adaptador OpenAI; otros proveedores deben aportar su adaptador concreto.

## Errores normalizados

El framework traduce errores particulares de un SDK a categorías comunes:

- `ProviderAuthenticationError`;
- `ProviderQuotaExceeded`;
- `ProviderRateLimited`;
- `ProviderUnavailable`;
- `ProviderExecutionError`.

Ejemplo:

```text
SDK específico
    ↓
"insufficient_quota"
    ↓
ProviderQuotaExceeded
    ↓
Agent Dev Kit puede explicar la situación y evaluar fallback
```

## Fallback no silencioso

La política inicial admite:

```yaml
fallback_policy: never
```

o:

```yaml
fallback_policy: ask
```

Con `ask`:

```text
Proveedor A agotó cuota
        ↓
hay Proveedor B configurado
        ↓
"¿Querés cambiar a B?"
        ↓
sí → reconstruir agentes con B
no → conservar el error original
```

El framework no cambia silenciosamente de proveedor.

## DAG y fallo de proveedor

Si un nodo de un DAG falla por proveedor:

- el nodo vuelve a estado `pending`;
- los nodos ya completados conservan su resultado;
- si el usuario aprueba el fallback, el runtime puede reconstruirse con el siguiente proveedor;
- la ejecución continúa desde el trabajo pendiente.

Esto evita ejecutar nuevamente todo el plan desde cero.

## Conversación y cambio de proveedor

El CLI conserva un transcript neutral para poder reinyectar contexto si se cambia de proveedor.

La librería también permite usar sesiones nativas del proveedor cuando una integración las suministra.

## ChatGPT

Instalar Agent Dev Kit dentro de un repositorio consumidor no hace que un chat de ChatGPT lo invoque automáticamente.

El CLI resuelve la **ejecución real local**.

Para que ChatGPT lo invoque directamente como herramienta se necesita además una interfaz conectable (por ejemplo un conector/tool server). Esa integración es una capa diferente y no debe confundirse con el runtime del framework.
