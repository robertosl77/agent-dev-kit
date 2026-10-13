# Agent Dev Kit privado conectado a ChatGPT (MCP)

## Alcance

Esta es la conexión **privada**, sin servidor HTTP público. Agent Dev Kit
conserva el proyecto consumidor fijo y expone MCP sólo en loopback; un
cliente de túnel aprobado en la misma máquina establece una conexión **saliente**
con OpenAI. No se necesita publicar un puerto ni entregar el código fuente del
framework al cliente de chat. El túnel no instala ni actualiza Agent Dev Kit.

El túnel y la autenticación/identidad son capacidades del servicio de OpenAI,
**no** autenticación añadida al servidor MCP local. No se debe usar esta
configuración como servidor multiusuario sin aislamiento y autenticación
adicionales.

## 1. Preparar Agent Dev Kit

Se requiere una versión instalada con el extra `mcp` y el extra del proveedor.
En un checkout de desarrollo:

```powershell
python -m pip install -e ".[mcp,anthropic]"
```

Se configura el proveedor y el modelo en
`<proyecto>/.agent-dev-kit/project.yaml`:

```yaml
provider:
  name: anthropic
  default_model: <modelo-disponible-en-tu-cuenta>
```

Se entrega su API key a través de una variable de entorno del **proceso que
ejecuta el servidor** (por ejemplo `ANTHROPIC_API_KEY`), no en el YAML, Git,
comandos impresos en logs ni el perfil del túnel.

## 2. MCP local (sin escritura)

Desde una ventana PowerShell con las credenciales del proveedor cargadas:

```powershell
agent-dev-kit mcp "RUTA_DEL_PROYECTO_CONSUMIDOR" --transport streamable-http --host 127.0.0.1 --port 8000
```

El endpoint privado es:

```text
http://127.0.0.1:8000/mcp
```

No utilizar `--allow-actions` durante las primeras pruebas. La opción sólo
debe habilitarse después de verificar el control de identidad, las aprobaciones
humanas y un repositorio de pruebas. En el plan personal que sólo admita MCP
de lectura, el host no tendrá capacidad de ejecutar herramientas de escritura.

Agent Dev Kit rechaza `--host 0.0.0.0` u otras interfaces públicas. **No**
abrir puertos, configurar port forwarding ni publicar una URL de desarrollo
sin un proxy de autenticación.

## 3. Secure MCP Tunnel

El operador crea un `tunnel_id` en la configuración de túneles de OpenAI
Platform y obtiene una clave **de runtime para tunnel-client** independiente
de la API key del proveedor de modelos.

Instalar `tunnel-client` desde el enlace oficial que muestre la configuración
del túnel o desde el release público verificado del repositorio
`openai/tunnel-client`. Verificar con `tunnel-client help quickstart`.

Configurar el perfil local usando el `tunnel_id` y la URL MCP loopback
`http://127.0.0.1:8000/mcp` como `mcp-server-url`. Seguir el asistente
o las instrucciones del `tunnel-client` instalado para almacenar la clave
**fuera del repositorio**. Probar y ejecutar ese perfil:

```powershell
tunnel-client doctor --profile local-agent-dev-kit --explain
tunnel-client run --profile local-agent-dev-kit
```

Estos comandos requieren que el perfil `local-agent-dev-kit` ya se haya
creado con `tunnel-client init`. Los nombres y opciones del asistente pueden
evolucionar; seguir la versión oficial instalada.

El equipo necesita salida HTTPS hacia el servicio de OpenAI; no necesita
abrir una conexión entrante de Internet a la PC. El túnel debe estar
asociado a la organización y al espacio de trabajo autorizados.

## 4. Crear la integración en ChatGPT

En un espacio de trabajo compatible y con permisos suficientes, ir a
**Plugins → Agregar servidor MCP personalizado → Conexión: Tunnel**.
Seleccionar el túnel autorizado o introducir su `tunnel_id`, completar
la autenticación que corresponda, revisar los permisos de las herramientas
y crear la integración. El cliente MCP sólo recibe las herramientas publicadas
por Agent Dev Kit; no recibe la implementación Python.

Disponibilidad: según documentación de OpenAI, los permisos de escritura MCP
completos se limitan actualmente a los planes de trabajo Business,
Enterprise/Edu y a sus políticas específicas. Los planes personales que
puedan crear integraciones pueden estar restringidos a herramientas
de lectura. Confirmar el acceso real en la UI antes de probar `/do`.

**Orden de pruebas:**
1. `agent_dev_kit_status`: identifica el proyecto correcto.
2. `agent_dev_kit_workflow_start(mode="plan")`: sólo Triage.
3. `agent_dev_kit_workflow_start(mode="propose")`: sólo lectura.
4. `/do` únicamente en repositorio descartable, con `--allow-actions`,
   permisos del cliente y aprobación humana explícita en cada etapa.

En un cliente/plan sin soporte de herramientas de escritura, el cuarto
paso no puede realizarse remotamente aunque el servidor local lo soporte.

## Protección y operación

- Ejecutar el servicio y el túnel con una cuenta de sistema de permisos
  mínimos. Mantener un único servidor activo por repositorio.
- No ofrecer `--allow-actions` por defecto; las aprobaciones de modelos MCP
  no sustituyen las verificaciones internas de rama, diff y confirmación.
- La API key del proveedor, clave de tunnel-client y credenciales GitHub son
  **tres credenciales independientes**. Nunca enviarlas al modelo.
- Restringir acceso al proyecto y al almacenamiento local de checkpoints.
- El túnel **no concede** acceso a repos privados de GitHub por sí mismo:
  `read_issue` usa sólo permisos Git explícitos configurados en el proceso.
- Si se interrumpe una operación con efectos sobre archivos/Git, hacer revisión
  manual; no repetir automáticamente `/do`.

## Límites actuales

- Esta vía **no** implementa un servicio multi-tenant ni un GitHub App.
- No se implementó OAuth propio. La seguridad de autenticación y acceso
  remoto corresponde al túnel y a los permisos del producto de OpenAI.
- No hay prueba extremo a extremo con una cuenta de ChatGPT conectada ni
  garantía de disponibilidad para todos los planes.
- No se ofrece un endpoint de producción público. Para terceros sin el túnel
  privado se necesitaría un servicio HTTPS seguro, identidad/OAuth,
  aislamiento por cliente y GitHub App con permisos mínimos.

## Documentación oficial

- [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [Developer mode y MCP en ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt)
