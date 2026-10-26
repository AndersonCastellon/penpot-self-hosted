# Phase 0 Research: Penpot Self-Host with MCP

**Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

All findings below were obtained on the user's Mac (Docker 29.4.0, Compose v5.1.2,
`linux/arm64`) against the real `2.18.4` images, using a throwaway stack with project name
`penpot-research`, ports `19001`/`18025`, and no volumes shared with anything else. That stack
was removed with `down -v` afterwards (0 containers and 0 volumes left). Source citations are
paths inside the Penpot repository at tag `2.18.4`.

Status legend: **Verified** = observed on the running images; **Source** = read in the tag
but not executed; **Hypothesis** = explanation not yet proven, with the task that proves it.

## R1. Health-check tooling per image (resolves deferred question 1)

| Service | Shell | `curl` | `wget` | `node` | Listens on | Chosen probe |
|---|---|---|---|---|---|---|
| `penpot-frontend` | `bash` | no | no | no | 8080 | `bash` + `/dev/tcp`, `GET /readyz` → `200` (**Verified**) |
| `penpot-backend` | `bash` | yes | no | no | 6060 | `curl -fsS http://127.0.0.1:6060/readyz` → `200` (**Verified**) |
| `penpot-exporter` | `bash` | yes | no | yes | 6061 | `curl -fsS http://127.0.0.1:6061/readyz` → `200` (**Verified**) |
| `penpot-admin-console` | **none** | no | no | yes (v24.20) | 3000 | `node` + `http.get`, `/admin-console/` → `307`; accept any status `< 500` (**Verified** with `http.get`) |
| `penpot-mcp` | **none** | no | no | yes (v24.22) | 4401 | `node` + `http.get`, `GET /mcp` → `406`; accept any status `< 500` (**Verified**) |
| `penpot-postgres` | yes | n/a | n/a | n/a | 5432 | upstream `pg_isready -U penpot` (already present) |
| `penpot-valkey` | yes | n/a | n/a | n/a | 6379 | upstream `valkey-cli ping` (already present) |
| `penpot-mailpit` | no | n/a | n/a | n/a | 8025 | image's own `["CMD","/mailpit","readyz"]` (**Verified** via `docker image inspect`) |

Sources: `docker/images/files/nginx.conf.template:169` (`/readyz` proxied to the backend),
`backend/src/app/health.clj` (`/readyz` returns 503 when offline),
`exporter/src/app/http.cljs:132` (`/readyz`), `docker/images/files/nginx-entrypoint.sh:71,90-91`
(backend `6060`, MCP `4401`/`4402`).

**Decision**: write an explicit `healthcheck:` for all eight services in the override, including
the three that already have one upstream or in the image. Explicit entries are what the merged-config
validator can check (the validator cannot see image-defined health checks).

**Rationale**: no single tool works everywhere, so the probe is per-service. The two hardened
images (`admin-console`, `mcp`) have no shell, so their probe MUST use the exec form
(`["CMD", "node", "-e", ...]`), never `CMD-SHELL`.

**Alternatives rejected**: adding `curl` through a derived image (violates "official images, no
forks"); a sidecar prober container (one more service, more surface); checking only that the
process is running (does not prove readiness).

**Notes**
- The frontend probe goes through nginx to the backend (`/readyz` is proxied), so a healthy
  frontend implies a ready backend.
- With a warm image cache, `/readyz` returned `200` within about 15 seconds of `up -d`.

## R2. `fetch()` fails against the admin console (new finding)

`node -e "fetch('http://127.0.0.1:3000/')"` inside `penpot-admin-console` fails with
`ECONNREFUSED`, yet raw TCP and `http.get` succeed on `127.0.0.1`, `::1`, `localhost` and the
container IP (HTTP `307`).

**Status: PROVEN on the running stack (task T033).** On `2.18.4` the admin console answers
`GET /admin-console/` with `307` and `Location: http://localhost:9001/#/auth/login?callback-url=...`.
`fetch` with `redirect: "manual"` returns `307`; default `fetch` (follows redirects) fails with
`ECONNREFUSED` because `localhost:9001` does not exist inside the container. The override's probe uses
`http.get`, which does not follow redirects.

**Original hypothesis**: `fetch` follows the `307`, and the redirect target is the public URI
(`http://localhost:9001/...`), which does not exist inside the container, so the *redirected*
request is what is refused. `http.get` does not follow redirects, which would explain the
difference.

**Decision**: the probe MUST NOT follow redirects (use `http.get`, or `fetch` with
`redirect: "manual"`). **Proof task**: a unit/smoke test that asserts the exact probe command
returns exit code `0` against the running admin console (see tasks).

## R3. MCP endpoint behaviour through the self-hosted instance (resolves option A risk)

All **Verified** against `http://127.0.0.1:19001`:

| Request | Result |
|---|---|
| `GET /mcp/stream` | `406` — body says the client must accept `text/event-stream` |
| `POST /mcp/stream?userToken=fake` `initialize` with `Accept: application/json, text/event-stream` | `200`, `Content-Type: text/event-stream`, header `mcp-session-id`, `serverInfo.name = "penpot"` |
| Same `POST` with **no** `userToken` | `200`, identical result |
| `tools/list` without the session header | `400` "Server not initialized" |

**Consequences**
1. Option A is confirmed working end to end at the transport level: nginx → `penpot-mcp:4401`
   works with no extra container and no extra published port.
2. **The `initialize` handshake does not validate the token.** Any process that can reach
   `127.0.0.1:9001` can open an MCP session. The token only matters when a Penpot browser tab
   (plugin) registers the same token over `/mcp/ws`, so real tool calls still need that pairing.
   This makes the `127.0.0.1` binding (FR-004) the actual access control for the transport.
   It MUST be documented and MUST NOT be described as "token-protected" anywhere.
3. The smoke test can prove the MCP route without a Penpot account: `POST initialize` →
   `200` plus an `mcp-session-id` header. It cannot prove tool calls (these need a logged-in tab).
   Tool calls are covered by the manual scenario in `quickstart.md`.

## R4. Docker Compose requirements (resolves deferred question 2)

- `ports: !override` works on Compose **v5.1.2**: the merged config contains only
  `host_ip: 127.0.0.1` for `9001→8080` and `8025→8025`; the upstream bindings are not added.
- The minimum version that supports `!override` is still **unverified** (only one version was tested).

**Decision**: do not gate on a version number. Gate on **behaviour**: the merged-config validator
asserts every published port has `host_ip == 127.0.0.1`. An old Compose that ignores `!override`
produces an extra all-interfaces binding and the validator fails with the offending port. The CLI
additionally prints the detected `docker compose version` in that error message.

**Alternative rejected**: hard-coding `>= 2.24` from memory (would be an unverified claim).

## R5. `docker compose config` without the Docker socket (design enabler)

Verified: inside `docker:cli`, with the project mounted read-only and **no** `/var/run/docker.sock`,
`docker compose -f docker-compose.yaml -f docker-compose.override.yaml config --format json` exits `0` and prints
the merged model. Rendering config is client-side.

**Decision**: the unit-test container gets no socket. Only the smoke-test container gets it
(R8), so the privileged surface is limited to one command.

## R6. Telemetry (resolves FR-019 mechanics)

- `backend/src/app/config.clj:323-325`: telemetry is active only when `:telemetry-enabled` is true,
  which appends `:enable-telemetry` to the flags. The target URI defaults to
  `https://telemetry.penpot.app/` (`config.clj:72`).
- Upstream compose sets `PENPOT_TELEMETRY_ENABLED: "true"` and `PENPOT_TELEMETRY_REFERER: compose`
  on `penpot-backend` (`docker-compose.yaml:178-179`).
- **Verified**: with the override `PENPOT_TELEMETRY_ENABLED: "false"` the backend starts, the variable
  is `false` inside the container, and the startup log no longer contains the word "telemetry" (it
  appeared once before the change).

**Decision**: override `PENPOT_TELEMETRY_ENABLED` to `"false"` on `penpot-backend`. The validator
asserts the value is `"false"` and that `PENPOT_FLAGS` does not contain `enable-telemetry`.

## R7. Observations that affect the spec or plan

| # | Observation | Effect |
|---|---|---|
| a | Pulling all images downloads about **6.7 GB** (exporter alone is 2.89 GB, backend 1.21 GB, frontend 919 MB, postgres 652 MB, admin-console 554 MB, mcp 285 MB, valkey 186 MB, mailpit 50 MB). | SC-001 ("under 15 minutes including image downloads") only holds above roughly 75 Mbit/s. **Proposed spec follow-up**: measure SC-001 from a warm image cache, and state the download size in the quickstart. |
| b | The `penpotapp/admin-console:2.18.4` image reports `appVersion 2.18.0-RC4-1-gd8dd1b8` in its logs. | The version guard MUST compare the **image tag**, not an application-reported version. |
| c | The host already runs other containers (unrelated project). Ports `9001` and `8025` were free at test time. | A busy port MUST be detected and named, never assumed free (spec edge case 1). A container cannot see the Mac's ports, so detection works from the error of `docker compose up` (see R11). |
| d | The upstream Compose file declares `penpot_postgres_v15` and `penpot_assets`. Volume names get the project prefix. | `.env.example` sets `COMPOSE_PROJECT_NAME=penpot` so volume names are stable (`penpot_penpot_postgres_v15`, `penpot_penpot_assets`) and are documented for FR-022. |
| e | Postgres stores its password inside the data directory on first initialisation. | Regenerating `.env` after first start does **not** change the database password and would lock the backend out. The generator therefore never overwrites an existing `.env` (already FR-008) and the docs MUST say so. |
| f | `claude mcp add` on Claude Code `2.1.310`: `-t/--transport {stdio,sse,http}`, `-s/--scope {local,user,project}` (default `local`), `-H/--header`. | See R9. |

## R8. Test-container design (resolves deferred question 3 inputs)

**Decision**: one "tools" image built from `docker:cli` plus Alpine `python3` and `pytest`.
- `test` service: project mounted read-only, **no socket**, runs unit tests (R5).
- `smoke` service: same image, **with** the host Docker socket mounted, because the smoke test must
  create and delete a stack. It is started only by the explicit `smoke` command.

**Rationale**: `docker:cli` already contains the Docker CLI and Compose plugin, so no binaries are
copied across libc variants. Using only the standard library plus `pytest` keeps dependencies minimal.

**Risk**: a container with the Docker socket can control the host's Docker. Mitigation: only the
smoke service has it, the image is built locally from a pinned base, and the smoke code is limited to
`compose` calls under the project name `penpot-smoke` (enforced by a unit test of the command builder).

**Alternatives rejected**: running the smoke test from a host shell script (logic would be untested
Bash); using host Python (violates Principle II).

## R9. Claude Code registration (resolves deferred question 3)

From `claude mcp add --help` (Claude Code 2.1.310, **Verified**):

```text
claude mcp add --transport http --scope user penpot "<connection-url>"
```

- `--scope user` stores the URL, and therefore the token, in the user's own Claude Code configuration
  outside the repository (clarification Q5, FR-024).
- The helper prints this command with the token **masked** and offers the unmasked form only through
  an explicit flag that writes to stdout and never to a log.
- The command is documented but never executed by the project's code.

## R10. Decisions on the remaining unknowns

| Unknown | Decision | Evidence |
|---|---|---|
| Wrapper entry point | A single Bash script `bin/penpot` that only dispatches to Docker. All logic lives in tested Python. | Keeps FR-002 ("one command") without host Python (FR-003). |
| Language for tools | Python (Alpine `python3` in the tools image) | Constitution II allows containerised Python; only stdlib plus `pytest`. |
| Test runner | `pytest` | Standard, minimal. |
| Merged-config source of truth | `docker compose config --format json` | R5. |
| Smoke stack isolation | Project `penpot-smoke`, own volumes, ports from `PENPOT_HTTP_PORT`/`PENPOT_MAIL_PORT` set to free high ports, `down -v` in a `finally` block | FR-023, R3, R7c. |
| Port variables | Override publishes `127.0.0.1:${PENPOT_HTTP_PORT:-9001}:8080` and `127.0.0.1:${PENPOT_MAIL_PORT:-8025}:8025` | Lets the smoke stack avoid the user's real ports (verified `!override` + interpolation pattern in R4). |

## R11. Host/container boundary (added after the consistency analysis)

**Problem**: containers without the Docker socket cannot see the Mac's listening ports, its
Docker volumes, or `docker compose ps` for the real stack. Several behaviours (busy ports,
health wait, refusing to regenerate secrets, smoke probes) silently assumed they could.

**Rule (decision)**: the Bash dispatcher on the host *collects facts* from the Mac's Docker and
passes them in; Python in the tools container only *decides* on them through pure functions that
are unit tested. Only the `smoke` container has the socket (R8).

| Fact | Collected by (host Bash) | Decided by (Python, pure) |
|---|---|---|
| Docker reachable | `docker info`; on failure Bash prints the fixed message itself, because the tools container cannot run without Docker | n/a (message covered by the dispatcher test with a `docker` shim) |
| Compose version | `docker compose version --short` | `preflight`: puts the version in the error text |
| Existing volumes | `docker volume ls --format '{{.Name}}'` piped to `init` | `envgen`: refuses to create `.env` if `<project>_penpot_postgres_v15` exists |
| Service states | `docker compose ps --format json` piped to `health-verdict` with elapsed seconds and limit | `healthwait.evaluate(snapshot, elapsed, limit)` returns healthy, pending or failed (names the service); Bash only sleeps and loops |
| Busy port | stderr of `docker compose up -d` | `preflight.explain_up_error(stderr)` finds the port; Bash adds a best-effort holder via `docker ps --filter publish=<port>` |
| Published bindings (smoke) | `docker inspect` inside the smoke container | `smoke`: `HostIp == 127.0.0.1` for every binding |

**Smoke probes**: the smoke container attaches itself to the disposable network
`penpot-smoke_penpot` (`docker network connect`) and probes `penpot-frontend:8080` by service name
for `GET /` and the MCP `initialize`. Reaching a loopback-published port from inside a container
(`host.docker.internal`) is **not** relied on and stays `[unverified]`. The "unreachable from the
LAN" guarantee is proven by `HostIp` inspection plus the manual check from the Mac in quickstart §3.

**Smoke configuration**: the smoke test generates a throwaway env in a temporary directory with the
same `envgen`, and never reads the user's `.env`.

**Verified during the analysis (throwaway probe, outside the project)**
- Compose autodiscovers `docker-compose.yaml` plus `docker-compose.override.yaml`, and `ports: !override` is honoured.
- `-p penpot-smoke` takes precedence over `COMPOSE_PROJECT_NAME` set in `.env`.

## R12. PENPOT_PUBLIC_URI is the browser origin (found in the browser test, after the plan was approved)

**Finding.** The frontend serves `config.js` with `penpotPublicURI = PENPOT_PUBLIC_URI` and the UI calls
`<PENPOT_PUBLIC_URI>/api/...`. Upstream fixes it at `http://localhost:9001`. Opening the UI on any other origin
(`http://127.0.0.1:19001` in the first browser attempt) made the browser block every API call (CORS) and left a blank page.
Earlier checks with `curl` (200 on `/`, `/readyz`, MCP `initialize`) could not see this, because curl does not enforce CORS.

**Consequences and decisions.**
1. The override sets `PENPOT_PUBLIC_URI: http://localhost:${PENPOT_HTTP_PORT:-9001}` on the four services that receive it
   (frontend, backend, exporter, admin console), so changing the port keeps the UI working. This also makes the README
   advice for a busy port correct (it was not, before this fix).
2. `composecheck` requires that value to equal `http://localhost:<published frontend port>` (data-model check added).
3. The address shown to the user is `localhost`. The MCP transport does not depend on the origin, so a client may use
   `127.0.0.1` for `/mcp/stream`.
4. Lesson recorded: checks that bypass the browser cannot prove the UI works. The e2e browser test is the proof.

## Outstanding items carried into tasks

1. Prove R2's redirect hypothesis, and that the exact `node -e` one-liners return exit `0` (tasks: healthcheck tests).
2. Verify that env-map merging overrides the list-form `POSTGRES_*` entries on `penpot-postgres` as expected.
3. Verify `docker:cli`-based tools image installs `python3`/`pytest` and builds for `arm64` and `amd64`.
4. Decide whether to amend the constitution to replace its `[unverified]` Compose minimum with the
   behaviour-based rule from R4 (optional wording change, PATCH).
5. Capture the exact Docker error strings for a busy port (another container versus another program)
   and encode them as test fixtures for `preflight.explain_up_error` (R11).
6. ~~Verify that the smoke container can attach itself to the disposable network and reach
   `penpot-frontend:8080` by name (R11).~~ **Done (task T049)**: from the `smoke` container (Docker socket mounted, OrbStack
   runtime) the disposable stack came up, `docker network connect penpot-smoke_penpot <self>` worked,
   `GET http://penpot-frontend:8080/` returned 200, MCP `initialize` returned 200 with `mcp-session-id`,
   `docker inspect` showed `127.0.0.1:<port>` bindings, `compose exec` ran a health check, and teardown left
   0 containers, 0 volumes and 0 networks.
7. Observe which browser tab becomes the active MCP tab when a second one connects, and record the
   exact failure message when no plugin is connected (spec edge cases 4 and 5).
