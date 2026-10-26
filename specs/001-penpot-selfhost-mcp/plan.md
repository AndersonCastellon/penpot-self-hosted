# Implementation Plan: Penpot Self-Host with MCP

**Branch**: `001-penpot-selfhost-mcp` | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-penpot-selfhost-mcp/spec.md`

## Summary

Run Penpot `2.18.4` on the user's Mac using the **unmodified official Compose file** plus a
project-owned `docker-compose.override.yaml`. The override pins versions, rebinds the two published ports
to `127.0.0.1`, adds explicit health checks to all eight services, disables telemetry, and moves
secrets to a git-ignored `.env`. MCP needs **no extra container**: the official stack already
contains `penpot-mcp` and the nginx routes `/mcp/stream` and `/mcp/ws` on the single published port.
This was proven on the real `2.18.4` images (research R3).

Project-owned code is small and fully containerised: a Python package (standard library plus
`pytest`) that generates `.env`, validates the merged Compose model, builds the masked Claude Code
registration command, and decides when the stack is healthy. A Bash dispatcher `bin/penpot` is the
single entry point: it collects facts from the Mac's Docker and hands them to those pure Python
functions (research R11). A disposable-stack smoke test proves the whole chain without touching the
user's data.

## Technical Context

**Language/Version**: Python 3 from Alpine's `python3` package inside a `docker:cli`-based tools image (exact image tag pinned during implementation); Bash for the dispatcher only (`bash` is also installed in the tools image so the dispatcher can be tested).

**Primary Dependencies**: Docker Engine 29.4.0 and Compose v5.1.2 on the host (verified); `pytest` in the tools image; no other third-party Python packages. Penpot images `penpotapp/{frontend,backend,exporter,admin-console,mcp}:2.18.4`, `postgres:15`, `valkey/valkey:8.1`, `axllent/mailpit:v1`.

**Storage**: Two Docker named volumes, `penpot_penpot_postgres_v15` (accounts and designs) and `penpot_penpot_assets` (uploads). No project-owned database.

**Testing**: `pytest` unit tests (no Docker socket) and one smoke test (socket mounted, disposable stack `penpot-smoke`). TDD: every test is written and seen failing before its code (Principle III).

**Target Platform**: macOS host with Docker Desktop; images are multi-arch (`amd64`, `arm64`), verified on `arm64`.

**Project Type**: Infrastructure configuration plus a small CLI toolset (no web or mobile app of our own).

**Performance Goals**: All 8 services healthy within 180 s on a warm start (SC-002, observed about 15 s to `/readyz`); unit suite under 60 s and smoke test under 300 s (SC-006).

**Constraints**: Docker-only runtime (nothing but Docker on the host); every published port on `127.0.0.1`; no secrets in git or output; official Compose file never edited; all code, comments and commits in English.

**Scale/Scope**: One user, one machine, one instance. Eight services, two published ports, eight Python modules.

No `NEEDS CLARIFICATION` remains. Items that need proof during implementation are listed in
`research.md` under "Outstanding items" and become test tasks, not open questions.

## Constitution Check

*GATE: passed before Phase 0 and re-checked after Phase 1 design. Constitution v1.1.0.*

| Rule | Status | How the design satisfies it |
|---|---|---|
| I. English-only code and commits | PASS | All source, comments, test names and commit messages in English. `docs/` may stay Spanish. |
| II. Docker-only runtime | PASS | Host needs Docker only. Python runs in the tools container; the host Bash dispatcher only calls `docker`. |
| III. Test-first (NON-NEGOTIABLE) | PASS | Task order is test → see it fail → implement, per module. |
| IV. Minimum unit coverage | PASS | Env generator, merged-config validator, MCP URL helper with masking, health-wait logic, preflight, smoke command builder, **the CLI commands, and the Bash dispatcher** (tested with a `docker` shim on the `PATH`): each has unit tests. |
| V. Simplicity and upstream-first | PASS | Upstream `docker-compose.yaml` copied unmodified; all changes in `docker-compose.override.yaml` (the names the constitution prescribes; Compose autodiscovers both, verified); no extra services. One justified exception below. |
| Pinned version `2.18.4` | PASS | `.env.example` fixes it; validator rejects any other tag, including upstream's `${PENPOT_VERSION:-2.18}` fallback. |
| Secrets only in git-ignored `.env` | PASS | Generator + `.gitignore` + masking everywhere + user-scope Claude registration. |
| Ports on `127.0.0.1` | PASS | `ports: !override`; validator checks `host_ip`; smoke test checks `docker inspect`. |
| Health check on every service | PASS | Eight explicit checks (research R1). |
| Named volumes for database and assets | PASS | Upstream volumes kept; names documented (FR-022). |
| Authoritative source = tag `2.18.4` | PASS | Every claim cites a path in the tag or an observation in `research.md`. |
| MCP via `enable-mcp`, remote endpoint, no host `npx` | PASS | Flag already in upstream `PENPOT_FLAGS`; endpoint verified. Local `@penpot/mcp` not used. |
| Documented caveats (single key, one active tab, tab must stay open) | PASS | In user docs and quickstart; token-validation statement added (research R3). |
| Containerised smoke test | PASS | `bin/penpot smoke`, disposable project `penpot-smoke`. |

**Post-design re-check**: no new violations. The constitution's `[unverified]` Compose minimum is
replaced in practice by a behaviour check (research R4); amending the wording is optional (PATCH) and
is listed as a task, not a blocker.

## Project Structure

### Documentation (this feature)

```text
specs/001-penpot-selfhost-mcp/
├── plan.md              # this file
├── research.md          # Phase 0: verified findings on the real images
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1: validation guide
├── contracts/
│   ├── cli.md           # bin/penpot commands, exit codes, errors, smoke contract
│   └── stack-interfaces.md  # ports, health checks, env overrides, MCP behaviour
├── checklists/requirements.md
└── tasks.md             # Phase 2: created later by /speckit-tasks
```

### Source Code (repository root)

```text
docker-compose.yaml           # byte-identical copy of docker/images/docker-compose.yaml @ 2.18.4 (never edited)
UPSTREAM.md                   # origin URL and SHA-256 of docker-compose.yaml; a unit test guards it
docker-compose.override.yaml  # pins, ports, health checks, telemetry, secrets (all project changes)
.env.example                  # placeholders only (`change-me`); PENPOT_VERSION=2.18.4, COMPOSE_PROJECT_NAME=penpot
.gitignore                    # .env, .mcp.json, caches
README.md                     # prerequisites, commands, volumes and `down -v` warning, MCP rules
bin/
└── penpot                    # Bash dispatcher: collects Docker facts; init|check|up|status|down|mcp-url|test|smoke
tools/
├── Dockerfile                # docker:cli + bash + python3 + pytest, pinned; pytest cache disabled
└── compose.tools.yaml        # services: test (no socket), tool (no socket), smoke (socket)
src/
└── penpot_selfhost/
    ├── masking.py            # mask secrets and tokens in any string
    ├── envgen.py             # create .env, never overwrite, refuse when the data volume exists
    ├── composecheck.py       # validate merged compose model (data-model checks)
    ├── mcpurl.py             # build/mask connection URL and `claude mcp add` command
    ├── healthwait.py         # pure evaluate(snapshot, elapsed, limit) -> healthy|pending|failed(service)
    ├── preflight.py          # explain `compose up` errors (busy port), Compose version in messages
    ├── smoke.py              # disposable-stack orchestration (project-name guard, retries, teardown)
    └── cli.py                # argument parsing, exit codes, command wiring, message formatting
tests/
├── unit/
│   ├── test_sanity.py
│   ├── test_upstream.py         # docker-compose.yaml still matches UPSTREAM.md
│   ├── test_masking.py
│   ├── test_cli_errors.py
│   ├── test_cli_commands.py     # command wiring with injected runners and the exact outputs of contracts/cli.md
│   ├── test_dispatch.py         # bin/penpot with a `docker` shim on PATH
│   ├── test_envgen.py
│   ├── test_composecheck.py     # includes deliberately broken fixtures (SC-007)
│   ├── test_real_override.py    # real `docker compose config` through composecheck
│   ├── test_mutations.py        # every deliberate mistake is caught
│   ├── test_mcpurl.py
│   ├── test_no_project_scope_mcp.py
│   ├── test_healthwait.py
│   ├── test_preflight.py
│   ├── test_smoke_commands.py   # guards: only project `penpot-smoke` is ever touched
│   ├── test_tools_compose.py    # only the smoke service may mount the Docker socket
│   ├── model_builder.py         # helper: builds merged-compose models for tests
│   ├── test_english_only.py     # FR-021 heuristic over code and config
│   ├── test_gitignore_and_example.py
│   └── test_no_secrets_in_repo.py
├── fixtures/                    # real Docker error text for a busy port and real `lsof` output (host program, runtime forwarder)
└── smoke/
    └── test_smoke.py            # runs only through `bin/penpot smoke`
docs/
└── 2026-10-25-penpot-self-host-design.md   # approved design (Spanish)
specs/001-penpot-selfhost-mcp/validation-notes.md   # measured evidence for SC-001 to SC-009 (created in Setup)
```

**Structure Decision**: single project, flat. `src/` already exists in the repo and holds the one
Python package; the Compose files live at the root so `docker compose` finds them with no flags.
No web/mobile split, no models/services layers: the code is a handful of pure functions with thin
I/O edges, which keeps every unit testable without Docker.

## Key Design Decisions

1. **Behaviour over version numbers for `!override`.** The validator inspects the merged result; an
   unsupported Compose cannot silently leave a port open (research R4).
2. **Explicit health checks everywhere, exec form only.** Two images have no shell (research R1).
3. **Redirects are never followed by probes.** Avoids the admin-console `fetch` failure (research R2).
4. **Socket only where unavoidable.** Unit tests and the `check` command run without the Docker
   socket (research R5, R8); only `smoke` mounts it.
5. **Disposable smoke stack.** Own project name, volumes, throwaway env and random high ports
   (retried if busy), removed in `finally` (FR-023); a unit test proves the command builder cannot
   name any other project. The smoke container probes by service name over the stack's own network.
6. **Honest MCP security model.** The transport accepts any token; the loopback binding is the access
   control. Docs say so (research R3).
7. **Port variables.** `PENPOT_HTTP_PORT` / `PENPOT_MAIL_PORT` let the smoke stack avoid the real ports
   and let the user resolve a busy port without editing Compose files.
8. **The host collects, Python decides.** Containers without the socket cannot see the Mac's ports,
   volumes or `compose ps`. The dispatcher gathers those facts and passes them to pure, unit-tested
   functions: busy port from the `compose up` error, health verdict from a `ps` snapshot, refusal to
   regenerate secrets from the volume list (research R11, contracts/cli.md).
10. **The browser origin is part of the configuration.** `PENPOT_PUBLIC_URI` follows `PENPOT_HTTP_PORT` and the user opens
    `localhost`, because the UI calls the API at that address and the browser blocks any other origin (research R12).
9. **Refuse before locking the user out.** `init` creates nothing when the real database volume exists
   but `.env` is missing, because Postgres keeps its first password (spec edge case 7, FR-008).

## Risks and Open Items

| # | Risk or item | Handling |
|---|---|---|
| 1 | First pull is about 6.7 GB; SC-001 originally depended on bandwidth. | Resolved: SC-001 now excludes the first download and the docs state the size (research R7a). |
| 2 | Admin-console probe: the redirect explanation (R2) is a hypothesis. | Test task asserts the exact probe returns exit `0` on the running service. |
| 3 | `POSTGRES_PASSWORD` is list-form upstream; override uses map-form. | Validator test on the merged model; fail loudly if the old literal survives. |
| 4 | Tools image on both architectures. | Build check task on `arm64` (host) and a documented `amd64` build. |
| 5 | MCP multi-user mode is marked "under development" upstream (`mcp/docs/multi-user-mode.md`). | Accepted risk, documented; pinned version limits drift. |
| 6 | Admin-console image logs `appVersion 2.18.0-RC4` under tag `2.18.4`. | Guard compares image tags only. |
| 7 | Tool calls cannot be automated without a logged-in browser tab. | Manual scenario in the quickstart; smoke covers the transport only. |
| 8 | The exact Docker wording for a busy port (container versus program) is unknown. | Capture both strings as fixtures before writing `explain_up_error` (research outstanding item 5). |
| 9 | Whether the smoke container can attach to the disposable network and resolve service names. | Verified by an early smoke-spike task (research outstanding item 6); fallback is `docker compose exec` probes. |
| 10 | The "plugin not connected" message and the winning tab on a second connection are upstream behaviour. | Observed and documented, not enforced (spec edge cases 4 and 5; research outstanding item 7). |
| 11 | Reaching a loopback-published port from inside a container is unproven. | Not relied on; `HostIp` inspection plus the manual LAN check cover FR-004 (research R11). |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| The `smoke` container mounts the Docker socket | The smoke test must create and delete a whole stack from inside a container, because the host has no Python (Principle II). | Running orchestration in host Bash leaves untested logic; running host Python breaks Principle II. Mitigation: socket only in `smoke`, command builder unit-tested to touch only `penpot-smoke`. |
| Bash dispatcher `bin/penpot` on the host | Gives the single-command UX (FR-002) without host Python, and is the only place that can see the Mac's Docker state. | `make` is not guaranteed on a fresh Mac; asking the user to type long `docker compose` commands fails FR-002. Kept to dispatch plus fact collection, and unit tested with a `docker` shim (`tests/unit/test_dispatch.py`) because Principle IV requires tests for scripts; the smoke test does not cover it. |
