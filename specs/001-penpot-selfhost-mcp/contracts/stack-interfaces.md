# Contract: stack interfaces (ports, health checks, MCP endpoint)

**Spec**: FR-004, FR-005, FR-009, FR-019, FR-020
Evidence: [research.md](../research.md) R1, R3, R6.

## Published ports (real stack)

| Host binding | Container | Service | Purpose |
|---|---|---|---|
| `127.0.0.1:${PENPOT_HTTP_PORT:-9001}` | `8080` | `penpot-frontend` | Penpot UI, `/mcp/stream`, `/mcp/ws` |
| `127.0.0.1:${PENPOT_MAIL_PORT:-8025}` | `8025` | `penpot-mailpit` | Mail catcher web UI |

No other service publishes a port. `4400`, `4401` and `4402` MUST NOT be published (FR-009).
Both bindings use `ports: !override` because Compose merges `ports` lists additively.

## Health checks (all eight services)

All exec-form (`["CMD", ...]`), never `CMD-SHELL`, because two images have no shell.

| Service | Probe | Pass condition |
|---|---|---|
| `penpot-frontend` | `bash` + `/dev/tcp/127.0.0.1/8080`, `GET /readyz` | status line contains ` 200 ` |
| `penpot-backend` | `curl -fsS -o /dev/null http://127.0.0.1:6060/readyz` | exit `0` |
| `penpot-exporter` | `curl -fsS -o /dev/null http://127.0.0.1:6061/readyz` | exit `0` |
| `penpot-admin-console` | `node` + `http.get` `127.0.0.1:3000/admin-console/`, no redirect following | status `< 500` |
| `penpot-mcp` | `node` + `http.get` `127.0.0.1:4401/mcp` | status `< 500` (`406` expected) |
| `penpot-postgres` | `pg_isready -U penpot` | exit `0` (upstream value kept) |
| `penpot-valkey` | `valkey-cli ping \| grep PONG` | exit `0` (upstream value kept) |
| `penpot-mailpit` | `/mailpit readyz` | exit `0` (image value, restated) |

Suggested timing for the five Penpot services: `interval 10s`, `timeout 5s`, `retries 6`,
`start_period 30s`. Final numbers are set in the implementation tasks after measuring.

## Browser origin (research R12)

The UI calls the API at `PENPOT_PUBLIC_URI`, so the user must open exactly `http://localhost:<PENPOT_HTTP_PORT>`.
The override sets `PENPOT_PUBLIC_URI` on `penpot-frontend`, `penpot-backend`, `penpot-exporter` and
`penpot-admin-console` to `http://localhost:${PENPOT_HTTP_PORT:-9001}`, and `bin/penpot check` fails if any of them differs.

## Environment overrides (names only; values come from `.env`)

| Variable | Service(s) | Why |
|---|---|---|
| `PENPOT_SECRET_KEY` | backend, exporter, admin-console | replace upstream literal (FR-007) |
| `PENPOT_DATABASE_PASSWORD` | backend, admin-console | replace upstream literal |
| `POSTGRES_PASSWORD` | postgres | replace upstream literal; same value as above |
| `PENPOT_TELEMETRY_ENABLED=false` | backend | FR-019 |
| `PENPOT_PUBLIC_URI=http://localhost:${PENPOT_HTTP_PORT}` | frontend, backend, exporter, admin-console | the browser origin must match the published port (research R12) |

`PENPOT_FLAGS` stays as upstream (`... enable-mcp enable-admin-console`); the telemetry flag is never added.

## MCP endpoint behaviour (observed on 2.18.4)

| Request to `http://127.0.0.1:<port>/mcp/stream[?userToken=...]` | Response |
|---|---|
| `GET` | `406 Not Acceptable` |
| `POST` `initialize`, `Accept: application/json, text/event-stream` | `200`, `text/event-stream`, header `mcp-session-id` |
| `POST` `tools/list` without session header | `400 Server not initialized` |

**Security statement (MUST appear in user docs):** the `initialize` handshake is accepted with any
token or none. Access to the transport is controlled by the `127.0.0.1` binding. The token only
pairs an MCP client with a browser tab whose plugin registered the same token over `/mcp/ws`.

## WebSocket route

`/mcp/ws` is proxied by nginx to `penpot-mcp:4402`. It is used by the browser plugin only. The
smoke test does not exercise it (it needs a logged-in tab); the manual scenario in
[quickstart.md](../quickstart.md) does.
