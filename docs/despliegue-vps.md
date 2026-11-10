# Despliegue de Penpot en el VPS

Penpot 2.18.4 publicado en `https://penpot.andersoncastellon.com` detrás del proxy del edge
(Traefik), con Let's Encrypt para el certificado.

Este documento describe cómo está montado en el VPS, cómo se reproduce y cómo operarlo.
Para el edge (Traefik, redes, rutas) consulta el repositorio `vps_edge`.

## Arquitectura

```
Internet ──443──> edge-traefik ──(red edge-penpot, alias penpot-web:8080)──> penpot-frontend
                                                                              │
                                  red privada "penpot" del proyecto           │
                  penpot-backend, penpot-exporter, penpot-admin-console,       │
                  penpot-mcp, penpot-postgres, penpot-valkey, penpot-mailpit <─┘
```

- Solo `penpot-frontend` está en la red `edge-penpot`. No publica ningún puerto en el host.
- Los servicios internos solo están en la red `penpot`.
- `penpot-mailpit` publica su UI en `127.0.0.1:8025` (solo accesible desde el VPS).

## Archivos del repo

| Archivo | Qué hace | Versionado |
|---|---|---|
| `docker-compose.yaml` | Compose oficial de Penpot 2.18.4, sin cambios (ver `UPSTREAM.md`). | Sí |
| `docker-compose.override.yaml` | Cambios del proyecto para localhost (secretos desde `.env`, versión fijada, health checks). | Sí |
| `docker-compose.vps.yaml` | Overlay del VPS: dominio público, red `edge-penpot`, sin puertos publicados, flags de producción. | Sí |
| `edge/penpot.yml` | Archivo de rutas para Traefik. Se instala con `edge-ctl route install`. | Sí |
| `.env` | Secretos y versión. Lo genera el VPS. | **No** (en `.gitignore`) |

## Flags de Penpot en el VPS

Definidas en `docker-compose.vps.yaml`:

| Flag | Estado | Motivo |
|---|---|---|
| `disable-email-verification` | activa | No hay SMTP real; Mailpit no entrega correo fuera del VPS. |
| `enable-smtp` | activa | Necesaria para que Penpot envíe a Mailpit. |
| `enable-mcp` | activa | Para conectar Claude Code. |
| `enable-admin-console` | activa | Panel de administración en `/admin`. |
| `enable-prepl-server` | **quitada** | Es un REPL remoto. No debe estar expuesto en internet. |
| `disable-secure-session-cookies` | **quitada** | Con HTTPS las cookies deben ser seguras. |
| `disable-registration` | activa | Registro cerrado una vez creada la cuenta de administrador. |

## Puesta en marcha

Requisitos: Docker con Compose v2.24 o posterior, el repo clonado y el registro DNS
`penpot.andersoncastellon.com` → IP del VPS.

```bash
cd ~/penpot-self-hosted

# 1. .env con secretos aleatorios (no se sobrescribe si ya existe)
umask 077
cat > .env <<EOF
PENPOT_VERSION=2.18.4
COMPOSE_PROJECT_NAME=penpot
PENPOT_HTTP_PORT=9001
PENPOT_MAIL_PORT=8025
PENPOT_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')
POSTGRES_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
EOF

# 2. Red del edge (ver el incidente de abajo si falla)
cd /opt/edge && ./scripts/edge-ctl network add penpot

# 3. Stack (la primera vez descarga unos 6.7 GB)
cd ~/penpot-self-hosted
docker compose --project-directory . \
  -f docker-compose.yaml -f docker-compose.override.yaml -f docker-compose.vps.yaml \
  up -d

# 4. Ruta en el edge
cd /opt/edge && ./scripts/edge-ctl route install penpot ~/penpot-self-hosted/edge/penpot.yml

# 5. Conectar Traefik a la red del proyecto (si no lo hizo network add)
docker network connect edge-penpot edge-traefik
```

`bin/penpot` no se usa en el VPS: sus comprobaciones están pensadas para localhost.

## Cuenta de administrador y registro

1. Con el registro abierto, crea tu cuenta en `https://penpot.andersoncastellon.com`
   con una contraseña robusta.
2. Cierra el registro: añade `disable-registration` a `PENPOT_FLAGS` en `docker-compose.vps.yaml`
   para `penpot-frontend`, `penpot-backend` y `penpot-exporter`, y vuelve a ejecutar `up -d`.
   Esto ya está aplicado en el VPS.
3. Comprueba que no se pueden crear cuentas nuevas.

## API key para el MCP

1. En Penpot: **Tu cuenta > Integraciones > MCP Server**, genera una key y cópiala (se muestra una sola vez).
2. Regístrala en Claude Code con `bin/penpot mcp-url`, pasando la key por variable de entorno.
   Así no queda en el historial ni en el repo.

Nota de seguridad: el endpoint MCP acepta cualquier token en el handshake. La key solo
empareja tu cliente con tu pestaña de Penpot, pero el endpoint está expuesto en internet.
Si quieres una capa extra, restringe la ruta `/mcp` por IP en Traefik.

## Operación

```bash
cd ~/penpot-self-hosted
COMPOSE="docker compose --project-directory . -f docker-compose.yaml -f docker-compose.override.yaml -f docker-compose.vps.yaml"

$COMPOSE ps              # estado de los servicios
$COMPOSE logs -f penpot-backend
$COMPOSE pull && $COMPOSE up -d   # actualizar (cambiar PENPOT_VERSION antes, con cuidado)
```

Nunca uses `docker compose down -v`: borra cuentas y diseños.

## Datos y copias de seguridad

| Volumen | Contiene |
|---|---|
| `penpot_penpot_postgres_v15` | Cuentas y diseños (Postgres). |
| `penpot_penpot_assets` | Imágenes y otros assets subidos. |

No hay copias automáticas. Antes de actualizar, haz un volcado de Postgres y copia el volumen de assets:

```bash
docker exec penpot-penpot-postgres-1 pg_dump -U penpot penpot | gzip > ~/backups/penpot-$(date +%F).sql.gz
```

Guarda también el `.env`: sin él no se puede abrir el volumen de Postgres, porque la contraseña queda fijada en el primer arranque.

## Incidencias conocidas

### `network add` falla con `network edge-demo not found`

El contenedor `edge-traefik` conservaba `NetworkMode: edge-demo`, un resto de la prueba
de humo del edge. Con ese modo, Docker no permite conectar el contenedor a ninguna red.

Diagnóstico:

```bash
docker inspect edge-traefik --format '{{.HostConfig.NetworkMode}}'
```

Si imprime `edge-demo`, recrea Traefik. Esto corta el servicio unos segundos para todos los sitios del VPS:

```bash
cd /opt/edge && docker compose up -d --force-recreate traefik
docker network connect edge-penpot edge-traefik
```

Tras esto, `edge-ctl network list` no muestra la red `edge-penpot`, porque el registro
se quedó sin escribir. La red funciona igual. Ver el incidente en el repo `vps_edge`.
