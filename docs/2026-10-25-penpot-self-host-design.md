# Penpot self-hosted en Docker con MCP — Idea inicial de diseño

- **Fecha:** 2026-10-25
- **Estado:** borrador para revisión (aún no hay código)
- **Versión de Penpot:** `2.18.4` (fijada, ver constitución v1.1.0)
- **Host objetivo:** macOS (Apple Silicon o Intel; las imágenes tienen `amd64` y `arm64`)
- **Cliente de IA:** Claude Code
- **Fuente de verdad:** https://github.com/penpot/penpot/tree/2.18.4
  (las rutas citadas abajo son relativas a ese tag)

## 1. Objetivo y criterio de éxito

Tener Penpot corriendo en Docker en este Mac, junto con el servidor MCP, de modo que
Claude Code pueda leer y modificar diseños de Penpot.

**Está listo cuando:**
1. `docker compose up -d` deja todos los servicios en estado `healthy`.
2. Penpot responde en `http://localhost:9001` y solo desde `127.0.0.1`.
3. Claude Code llama a una herramienta MCP de Penpot y recibe una respuesta válida.
4. Las pruebas unitarias y el smoke test pasan, todo dentro de contenedores.

## 2. Decisión: MCP remoto servido por la propia instancia (opción A)

Se descarta el MCP local (`npx @penpot/mcp`) porque corre con Node en el host, incumple
la regla de "solo Docker" y su plugin se carga desde `design.penpot.app`.

El compose oficial del tag `2.18.4` **ya incluye** el MCP, así que no hace falta ningún
contenedor adicional:

| Hecho verificado | Fuente |
|---|---|
| Servicio `penpot-mcp` con imagen `penpotapp/mcp` | `docker/images/docker-compose.yaml:212-216` |
| Flag `enable-mcp` ya presente en `PENPOT_FLAGS` | `docker/images/docker-compose.yaml:27` |
| nginx del frontend enruta `/mcp/ws` y `/mcp/stream` | `docker/images/files/nginx-mcp-locations.conf.template:1-13` |
| Destinos por defecto: `penpot-mcp:4401` (HTTP) y `penpot-mcp:4402` (WebSocket) | `docker/images/files/nginx-entrypoint.sh:90-91` |
| El contenedor arranca con `node index.js --multi-user` | `docker/images/Dockerfile.mcp:57` |
| Escucha en `0.0.0.0` dentro del contenedor | `docker/images/Dockerfile.mcp:50` |
| Puertos del servidor: 4401 (HTTP) y 4402 (WebSocket del plugin) | `mcp/README.md:264-266` |
| Todo entra por un único puerto publicado: `9001` | `docker/images/docker-compose.yaml:95` |
| Las 5 imágenes existen en Docker Hub con tag `2.18.4` (`amd64` y `arm64`) | consulta a Docker Hub |

**Consecuencia:** no se publican los puertos 4400, 4401 ni 4402. El tráfico MCP viaja por
el mismo puerto `9001` que la interfaz de Penpot.

**Riesgo conocido:** `mcp/docs/multi-user-mode.md:3-5` marca el modo multiusuario como
"en desarrollo, solo para pruebas". Es el modo con el que arranca la imagen oficial, así
que se asume y se documenta.

## 3. Arquitectura

```
Claude Code ──HTTP──▶ 127.0.0.1:9001/mcp/stream?userToken=… ─┐
                                                              ▼
Navegador (pestaña de Penpot + plugin MCP) ──WS──▶ 127.0.0.1:9001/mcp/ws
                                                              │
                                              penpot-frontend (nginx)
                                                 │         │        │
                                       penpot-backend  penpot-mcp  penpot-exporter
                                          │      │         (4401 / 4402)
                                 penpot-postgres  penpot-valkey
```

Servicios del compose oficial (`docker/images/docker-compose.yaml`):

| Servicio | Imagen | Notas |
|---|---|---|
| `penpot-frontend` | `penpotapp/frontend` | nginx; único servicio con puerto publicado (`9001:8080`) |
| `penpot-backend` | `penpotapp/backend` | usa Postgres y Valkey; volumen de assets |
| `penpot-mcp` | `penpotapp/mcp` | servidor MCP en modo multiusuario |
| `penpot-exporter` | `penpotapp/exporter` | exportaciones |
| `penpot-admin-console` | `penpotapp/admin-console` | consola de administración (flag `enable-admin-console`) |
| `penpot-postgres` | `postgres:15` | volumen `penpot_postgres_v15` |
| `penpot-valkey` | `valkey/valkey:8.1` | notificaciones y estado de exportaciones |
| `penpot-mailpit` | `axllent/mailpit:v1` | SMTP temporal; interfaz en `8025` |

## 4. Estructura del proyecto

> Actualizado tras la implementación. La estructura inicial propuesta aquí (`scripts/`, header en el compose)
> cambió: el detalle vigente está en `specs/001-penpot-selfhost-mcp/plan.md`.

```
docker-compose.yaml           # copia idéntica byte a byte del upstream 2.18.4 (nunca se edita)
UPSTREAM.md                   # origen y SHA-256 del compose; un test lo vigila
docker-compose.override.yaml  # todas nuestras correcciones (sección 5)
.env.example                  # solo placeholders; PENPOT_VERSION=2.18.4
.env                          # secretos reales; ignorado por git
.gitignore
README.md                     # uso, volúmenes, advertencia de `down -v`, conexión MCP
bin/penpot                    # único punto de entrada: init, check, up, status, down, mcp-url, test, smoke
tools/                        # imagen y compose de las herramientas (Python y pytest, todo en contenedor)
src/penpot_selfhost/          # envgen, composecheck, healthwait, preflight, mcpurl, masking, smoke, cli
tests/                        # unit (pytest, sin socket de Docker), smoke (con socket, stack desechable) y fixtures
docs/                         # esta idea y notas, en español
specs/001-penpot-selfhost-mcp/# spec, plan, tareas, investigación y notas de validación
```

El código y los comentarios van en inglés; `docs/` puede ir en español (constitución, principio I).

> **Corrección posterior (prueba con navegador real).** La interfaz de Penpot llama a su API en
> `PENPOT_PUBLIC_URI` (upstream: `http://localhost:9001`). Abrirla en otro origen, por ejemplo `127.0.0.1`, o cambiar
> el puerto sin ajustar esa variable, deja la página en blanco por CORS. Las comprobaciones con `curl` no lo detectan.
> El override ahora hace que `PENPOT_PUBLIC_URI` siga a `PENPOT_HTTP_PORT`, `bin/penpot check` lo verifica y la URL
> que se debe abrir es siempre `http://localhost:<puerto>`.

## 5. Qué corrige el override

El compose oficial incumple cuatro reglas de la constitución. El override las resuelve
sin editar el archivo upstream:

| Problema en upstream | Corrección en `docker-compose.override.yaml` |
|---|---|
| Versión flotante `${PENPOT_VERSION:-2.18}` (líneas 92, 133, 195, 213, 219) | `.env` define `PENPOT_VERSION=2.18.4`; una prueba comprueba que ninguna imagen Penpot use otro tag |
| `9001` y `8025` publicados en todas las interfaces (líneas 95 y 308) | `ports: !override` con `127.0.0.1:9001:8080` y `127.0.0.1:8025:8025` |
| Sin healthcheck en frontend, backend, exporter, admin-console y MCP (solo lo tienen Postgres y Valkey) | healthchecks añadidos por servicio |
| `PENPOT_SECRET_KEY` y credenciales de Postgres escritas en el compose (líneas 49, 55-56, 270-271) | se leen desde `.env` con generación aleatoria |

> **Por qué `!override`:** Compose fusiona las listas `ports` de varios archivos sumándolas.
> Un override que solo añada `127.0.0.1:9001:8080` dejaría también el `9001:8080` original,
> publicado en todas las interfaces. Requiere Docker Compose v2.24 o superior
> `[unverified: versión mínima exacta de !override]`.

## 6. Flujo de conexión de Claude Code

1. Arrancar el stack y abrir `http://localhost:9001`; crear la cuenta local.
   Con `disable-email-verification` activo (línea 27) no hace falta confirmar por correo.
2. En Penpot: **Your account → Integrations → MCP Server**, activar el interruptor y generar
   la clave. Se muestra una sola vez y no es recuperable (`docs/mcp/index.md:75-76,121-122`).
3. Copiar la **server URL** que Penpot muestra; ya incluye la clave
   (`docs/mcp/index.md:127`). Su forma es `http://localhost:9001/mcp/stream?userToken=<clave>`.
4. Registrar el servidor en Claude Code (el comando exacto se valida en el smoke test):
   `claude mcp add --transport http penpot "<URL>"` `[unverified: sintaxis exacta del cliente]`.
5. Abrir un archivo de diseño y elegir **File → MCP Server → Connect**
   (`docs/mcp/index.md:145`).

**Reglas operativas (documentar en el README del proyecto):**
- Cada usuario tiene una sola clave. Regenerarla revoca la anterior de inmediato y cualquier
  cliente que la use deja de funcionar.
- Solo una pestaña del navegador puede ser la pestaña MCP activa a la vez
  (`docs/mcp/index.md:78`).
- La pestaña debe seguir abierta y despierta durante toda la sesión del agente; si el
  navegador la descarga, el plugin se desconecta (`docs/mcp/index.md:151-159`).
- La URL contiene la clave: no debe aparecer en logs, en la salida de `docker inspect`
  ni en commits.

## 7. Estrategia de pruebas (TDD, todo en contenedor)

**Unitarias** (`pytest` en contenedor, escritas antes del código):
- Generador de `.env`: produce claves aleatorias suficientemente largas, no sobrescribe un
  `.env` existente y nunca imprime secretos.
- Validador del compose fusionado (`docker compose config`): `PENPOT_VERSION` es `2.18.4`,
  todas las imágenes Penpot usan ese tag, todo puerto publicado está en `127.0.0.1`, todo
  servicio tiene healthcheck, existen los volúmenes con nombre.
- Helper MCP: construye la URL de conexión y enmascara siempre el token en cualquier salida.
- Lógica de espera de salud: reintentos, tiempo máximo y mensajes de error claros.

**Smoke test** (contenedor con acceso al stack):
- Levanta el stack y espera a que todos los servicios estén `healthy`.
- Comprueba que `GET /` responde y que `/mcp/stream` responde con un código distinto de 404.
- Comprueba que `9001` y `8025` no están accesibles desde otra interfaz que `127.0.0.1`.

## 8. Riesgos y dudas abiertas

| # | Riesgo o duda | Estado | Cómo se resuelve |
|---|---|---|---|
| 1 | Las imágenes MCP se construyen sobre `dhi.io/node` (imagen endurecida); probablemente sin `curl` ni `sh`. El healthcheck tendría que ser `node -e "fetch(...)"` | `[unverified]` | Inspeccionar la imagen en el primer paso del plan |
| 2 | Qué herramienta de healthcheck traen las imágenes de frontend, backend, exporter y admin-console | `[unverified]` | Probar `docker run … sh -c 'command -v curl wget'` por imagen |
| 3 | Versión mínima exacta de Compose para `!override` | `[unverified]` | Probar con `docker compose version` y `config` |
| 4 | Modo multiusuario del MCP marcado como "en desarrollo" | Aceptado | Documentado; el smoke test lo ejercita |
| 5 | El plugin MCP corre en el navegador: Chromium puede restringir conexiones a `localhost` desde otro origen | Poco probable aquí | La pestaña se sirve desde el mismo origen (`localhost:9001`), pero se confirma con el smoke test |
| 6 | Telemetría de Penpot activada por defecto (`PENPOT_TELEMETRY_ENABLED: "true"`, línea 178) | Decisión pendiente | Decidir si el override la desactiva |
| 7 | Mailpit y la consola de administración: ¿se mantienen? | Decisión pendiente | Por YAGNI se podrían quitar, pero `enable-admin-console` y el SMTP forman parte del stack oficial |

## 9. Siguientes pasos

1. Revisar y aprobar este documento.
2. Pasar al plan de implementación (skill `writing-plans`), con tareas en orden TDD.
3. Primer hito del plan: resolver las dudas 1 a 3 con pruebas reales contra las imágenes
   `2.18.4` antes de escribir el override definitivo.
