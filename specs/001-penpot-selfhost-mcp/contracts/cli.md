# Contract: `bin/penpot` command line

**Spec**: FR-002, FR-008, FR-011, FR-014, FR-016, FR-018, FR-023
**Design rule**: [research.md](../research.md) R11, "the host collects, Python decides".

`bin/penpot` is a Bash dispatcher with two jobs: choose where a command runs, and *collect facts*
from the Mac's Docker (reachability, Compose version, volume names, `compose ps` snapshots, the
error text of `compose up`). Every decision made from those facts is a pure Python function in the
tools container and is unit tested. The dispatcher itself is unit tested with a `docker` shim on the
`PATH` (see `tests/unit/test_dispatch.py`).

Conventions: exit code `0` = success, `1` = check failed (the tool ran correctly and found a
problem), `2` = usage error or missing prerequisite. Errors go to stderr. No command ever prints a
secret; secrets are masked as in [data-model.md](../data-model.md).

| Command | Runs in | Purpose | Success output |
|---|---|---|---|
| `bin/penpot init` | host Bash collects volume names, tools container decides | Create `.env` with generated secrets. If `.env` exists: change nothing, print "`.env` already exists, left untouched", exit `0`. If `.env` is absent but the real stack's database volume exists: create nothing, exit `1`, explain recovery (FR-008, spec edge case 7). | `created .env (PENPOT_VERSION=2.18.4)` |
| `bin/penpot check` | tools container (no socket) | Run the merged-config validator on `docker-compose.yaml` + `docker-compose.override.yaml` + `.env`. | `OK: 8 services, 5 images pinned to 2.18.4, 2 ports local-only` |
| `bin/penpot up` | host Bash loop, tools container decides | Check Docker is reachable, run `docker compose up -d`, explain a failure, then loop: `compose ps` snapshot → verdict until healthy, failed or timed out. | `healthy: 8/8 in 41s — http://localhost:9001` |
| `bin/penpot status` | host Docker, tools container formats | One line per service: name, state, health. | table |
| `bin/penpot down` | host Docker | `docker compose down` **without** `-v`. | `stopped (volumes kept)` |
| `bin/penpot mcp-url` | tools container | Print the Claude Code registration command and operating rules. Reads the token from the `PENPOT_MCP_TOKEN` environment variable or a hidden prompt, never from argv. | masked `claude mcp add --transport http --scope user penpot "http://127.0.0.1:9001/mcp/stream?userToken=ab…"` |
| `bin/penpot test` | tools container (no socket) | Run all unit tests. | pytest summary |
| `bin/penpot smoke` | tools container (**socket mounted**) | Disposable-stack smoke test (FR-016, FR-023). | `smoke OK in 74s; stack penpot-smoke removed` |

## Internal subcommands (called by the dispatcher, not by the user)

| Subcommand | Input | Output |
|---|---|---|
| `explain-up-error` | stderr of `docker compose up -d` on stdin | the "port busy" message, or a generic one with the original text |
| `health-verdict --elapsed N --limit L` | `docker compose ps --format json` on stdin | `healthy` (exit 0), `pending` (exit 3), or the failure message (exit 1) |
| `format-status` | `docker compose ps --format json` on stdin | the status table |

## Error contract (FR-018)

| Situation | Produced by | Exit | Message pattern |
|---|---|---|---|
| Docker missing or daemon down | Bash dispatcher (the tools container cannot run without Docker) | 2 | `Docker is not reachable. Start your Docker runtime (Docker Desktop, OrbStack, ...) and retry.` |
| Compose does not apply the port restriction | `check` / `up` | 1 | `Port <port> of <service> is published on <addr>, expected 127.0.0.1. Detected Compose <version>; this version does not apply the port override, upgrade Docker Compose.` |
| Port busy | `explain-up-error` | 1 | `Port <port> is already in use (<another container: name> / another program). Set PENPOT_HTTP_PORT or PENPOT_MAIL_PORT in .env, or free the port.` |
| Service not healthy by deadline | `health-verdict` | 1 | `Service <name> is <state>/<health> after <n>s (limit <limit>s). Run: docker compose logs <name>` |
| Wrong or floating version | `check` | 1 | `Image <image> uses tag <tag>; expected 2.18.4.` |
| Invalid `.env` | `check` / `init` | 1 | `.env: <KEY> <problem>` (value never shown) |
| `.env` missing but data volume exists | `init` | 1 | `Database volume <name> already exists but .env is missing. New secrets would lock you out of your data. Restore your previous .env, or remove the volumes on purpose (this deletes all accounts and designs).` |

The exact Docker wording for a busy port (another container versus another program) is captured as a
test fixture before `explain-up-error` is written (research outstanding item 5).

## Timing limits (documented, used by SC-002 and FR-018)

| Phase | Default limit |
|---|---|
| Wait for healthy on warm start | 180 s |
| Wait for healthy on first start (images already pulled) | 300 s |
| Smoke test, end to end, warm images | 300 s |

## Smoke test contract (FR-016, FR-023)

The smoke container is the only one with the Docker socket, and it follows the same rule: it asks
Docker for facts and decides in tested functions.

1. Refuse to start if the project name resolves to anything other than `penpot-smoke`.
2. Generate a throwaway env file in a temporary directory with the same `envgen` (never read the
   user's `.env`), with a random port pair in 20000–59999. If `compose up` reports a busy port
   (`explain-up-error`), retry with a new pair, at most 3 times.
3. `up -d` under project `penpot-smoke`; wait for healthy with the same `evaluate` function as `up`.
4. Attach the smoke container itself to the network `penpot-smoke_penpot`
   (`docker network connect`) and probe by service name:
   `GET http://penpot-frontend:8080/` returns `200`; `POST /mcp/stream` with an `initialize` body and
   `Accept: application/json, text/event-stream` returns `200` and an `mcp-session-id` header
   (research R3).
5. Assert port bindings from `docker inspect` (`HostIp == 127.0.0.1` for every binding). Reachability
   of the published port from inside a container is not asserted (research R11).
6. Run each service's own healthcheck command through `docker compose exec` and require exit `0`.
7. In a `finally` block: disconnect the smoke container from the network, run `down -v` for project
   `penpot-smoke` only, and verify zero containers, volumes and networks remain for that project.
   Never invoke any `docker` command naming another project.
