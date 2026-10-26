# Data Model: Penpot Self-Host with MCP

**Date**: 2026-10-25 | **Spec**: [spec.md](spec.md) | **Research**: [research.md](research.md)

This feature has no application database of its own. The "data" is configuration, a few
runtime facts about the stack, and values the tools parse. Entities map to the spec's Key Entities.

## Entity: ConfigFile (`.env`)

Private settings of one installation. Never tracked by git. `.env.example` is its tracked,
placeholder-only counterpart.

| Field | Type | Rule |
|---|---|---|
| `PENPOT_VERSION` | string | MUST equal `2.18.4` exactly (FR-001). Floating tags rejected. |
| `COMPOSE_PROJECT_NAME` | string | MUST be `penpot` for the real stack (stable volume names). |
| `PENPOT_SECRET_KEY` | secret string | Generated; at least 64 URL-safe characters; unique per install. |
| `POSTGRES_PASSWORD` | secret string | Generated; at least 32 URL-safe characters. Same value feeds `PENPOT_DATABASE_PASSWORD`. |
| `PENPOT_HTTP_PORT` | integer | Default `9001`; range 1024–65535. |
| `PENPOT_MAIL_PORT` | integer | Default `8025`; range 1024–65535. |

**Lifecycle**: `absent → generated → in use`. The generator never moves a file out of
`in use`: if `.env` exists it is left untouched and the tool says so (FR-008, research R7e).
No transition regenerates secrets, because the database keeps the first password it saw.

**Refusal rule (spec edge case 7, FR-008)**: when `.env` is absent but the database volume of the
real stack (`<project>_penpot_postgres_v15`) already exists, `init` creates nothing, exits `1`, and
explains the recovery: restore the previous `.env`, or remove the volumes deliberately and accept the
data loss. The list of existing volume names is collected by the host dispatcher and passed in
(research R11); the generator itself never calls Docker. The smoke test passes an empty list because
its project has no volumes yet.

**Validation errors** (each names the offending key, never the value): missing key, wrong version,
secret too short, port out of range, port equal to the other port.

## Entity: PenpotInstance (runtime view)

The set of services started by Compose. Not stored; derived from `docker compose ps --format json`.

| Field | Type | Rule |
|---|---|---|
| `service` | string | One of the 8 services: `penpot-frontend`, `penpot-backend`, `penpot-mcp`, `penpot-exporter`, `penpot-admin-console`, `penpot-postgres`, `penpot-valkey`, `penpot-mailpit`. |
| `image_tag` | string | For the five `penpotapp/*` images MUST equal `PENPOT_VERSION`. |
| `state` | enum | `created`, `running`, `exited`, `restarting`, ... as reported by Compose. |
| `health` | enum | `healthy`, `unhealthy`, `starting`, or empty when no check exists (empty is a violation, FR-005). |
| `published_ports` | list | Each entry needs `host_ip == 127.0.0.1` (FR-004). |

**State machine of the stack** (used by the health-wait logic):

```text
absent --up--> starting --all healthy--> healthy --down--> stopped --up--> starting
                  |                          |
                  +--timeout / any exited--> failed (names the service)
```

`failed` is reported with the name of the first service that is `unhealthy`, `exited`, or still
`starting` at the deadline (FR-018).

The transition logic is one pure function, `evaluate(snapshot, elapsed_seconds, limit_seconds)`,
that returns `healthy`, `pending` or `failed(service, state)`. It owns no clock and no sleep: the
host dispatcher supplies each snapshot and the elapsed time (research R11).

## Entity: MergedComposeModel (validator input)

The JSON from `docker compose config --format json` for the base file plus the override.

Checks run against it (each is one unit test; all MUST fail on a deliberately broken fixture, SC-007):

| Check | Failure message names |
|---|---|
| Five `penpotapp/*` images share the tag `PENPOT_VERSION` and it equals `2.18.4` | the image |
| No image tag is `latest`, empty, or a floating `2.18` | the image |
| Every published port has `host_ip == 127.0.0.1` | the port |
| Every service defines `healthcheck.test` | the service |
| `penpot-backend` has `PENPOT_TELEMETRY_ENABLED == "false"` and flags lack `enable-telemetry` | the variable |
| `PENPOT_SECRET_KEY` and DB credentials are not the upstream literals | the variable (not the value) |
| Named volumes for database and assets exist and are mounted | the volume |
| No service other than `penpot-frontend` and `penpot-mailpit` publishes a port | the service |
| `PENPOT_PUBLIC_URI` of frontend, backend, exporter and admin console equals `http://localhost:<published frontend port>` (the browser origin; research R12) | the variable and service |
| The set of services is exactly the 8 expected names: none missing (for example the admin console or the mail catcher), none extra (FR-009, FR-020) | the service |

## Entity: McpKey / ConnectionAddress

| Field | Type | Rule |
|---|---|---|
| `base_url` | URL | `http://127.0.0.1:<PENPOT_HTTP_PORT>` for the real stack. |
| `path` | string | Fixed `/mcp/stream`. |
| `user_token` | secret string | Opaque. Obtained by the user from Penpot; shown once; never stored by the project. |
| `masked` | string | The URL with the token replaced by `****` plus the last 4 characters at most. |

**Rules**
- Any string representation produced by the helper is masked unless the caller passes the explicit
  `--reveal` flag, and even then it goes to stdout only, never to a log or a file (FR-011).
- A token shorter than 8 characters is fully masked (so the last-4 rule cannot leak it).
- The unmasked URL is held only in memory for the duration of the command.

**Helper output** (see [contracts/cli.md](contracts/cli.md)): the `claude mcp add` command with
`--scope user` (FR-024) and a reminder of the operating rules (FR-012).

## Entity: McpPluginSession (documented, not implemented)

Lives in the user's browser. Only one is active at a time; it ends when the tab is closed or
unloaded; regenerating the key revokes the previous one. The project stores nothing about it.
Its absence is what produces the "plugin not connected" failure in User Story 2, scenario 4.

## Entity: Volume

| Name (real stack) | Holds | Deleted by |
|---|---|---|
| `penpot_penpot_postgres_v15` | accounts, design files, settings | `docker compose down -v` |
| `penpot_penpot_assets` | uploaded images and other assets | `docker compose down -v` |

Both are named volumes (constitution, "Persistence"). The names follow from
`COMPOSE_PROJECT_NAME=penpot` and the upstream volume names; FR-022 documents them.
The smoke stack uses `penpot-smoke_*` volumes, which are disjoint from the real ones (FR-023).
