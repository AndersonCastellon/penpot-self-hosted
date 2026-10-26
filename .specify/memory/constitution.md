<!--
Sync Impact Report
- Version change: 1.1.0 → 1.2.0 (MINOR: materially expanded guidance; no rule removed or redefined)
- Modified principles: none renamed. Principle IV (Minimum Unit Coverage) expanded with the
  host-collects/Python-decides rule and the dispatcher and socket tests.
- Expanded rules:
  - Infrastructure & Security Constraints: Secrets (init refuses when the data volume exists), Network exposure
    (the unverified Compose minimum is replaced by a behaviour-based rule; ports checked before start),
    Docker runtime neutrality (new bullet).
  - Penpot & MCP Integration Rules: Browser origin (new bullet), Smoke test (real-browser verification added).
- Added sections: none (new rules added inside existing sections)
- Removed sections: none. Removed text: the "[unverified: exact minimum for !override]" marker.
- Templates reviewed (read at runtime, not modified here): plan-template.md,
  spec-template.md, tasks-template.md, checklist-template.md
- Deferred items: none
-->
# Penpot Self-Host Constitution

## Core Principles

### I. English-Only Code and Commits
All source code, identifiers, code comments, configuration comments, test names,
scripts, and commit messages MUST be written in English. Documents under `docs/`
(ideas, notes, brainstorming) MAY be written in Spanish.
Rationale: one language keeps the codebase searchable and reviewable by any
contributor or AI agent without translation drift.

### II. Docker-Only Runtime
Every runtime component (Penpot frontend, backend, Postgres, Valkey/Redis,
exporter, and MCP access) MUST run through `docker compose`. Nothing MAY require
a runtime installed on the host: no host Node.js, no `npx`, no host Python. When
Python is strictly necessary (helper scripts, tests), it MUST run inside a
container as well. The host needs only Docker.
Rationale: the target is a reproducible setup on a macOS host with no toolchain
pollution; the local `npx @penpot/mcp` server violates this rule.

### III. Test-First Development (NON-NEGOTIABLE)
TDD is mandatory. For every behavior change: write a failing test, confirm it
fails for the right reason, implement the minimum code to pass, then refactor
(Red-Green-Refactor). Code without a prior failing test MUST NOT be merged.
A guard test that passes on its first run MUST have its red phase demonstrated by
temporarily breaking the guarded thing.
Rationale: infrastructure glue (env generation, health checks, connection
helpers) breaks silently; tests written first define the contract.

### IV. Minimum Unit Coverage of Critical Parts
Unit tests MUST cover every important part: scripts, configuration generators
and validators, health-check logic, and MCP connection helpers. Tests MUST run
in a container with a single documented command and MUST pass before any change
is considered complete. Pure upstream configuration is not unit-tested; it is
verified by the smoke tests in Principle V and the workflow below.

- **Host collects, Python decides.** Containers without the Docker socket cannot
  see the Mac's listening ports, its Docker volumes, or `docker compose ps`.
  `bin/penpot` MUST collect those facts on the host and pass them in; every
  decision MUST be a pure Python function covered by unit tests.
- **The dispatcher is code.** `bin/penpot` itself MUST be unit tested with a fake
  `docker` (and `lsof`) first on `PATH`.
- **The socket is exceptional.** Only the smoke service MAY mount the Docker
  socket, and a unit test MUST fail if any other tools service does.

Rationale: coverage is targeted at code we own, not at upstream images; keeping
decisions pure keeps them testable without a Docker daemon, and keeping the
socket out of the test services limits what a test container can do to the host.

### V. Simplicity and Upstream-First
Start with the minimal official Penpot stack and add nothing beyond what a
written requirement demands (YAGNI). Customization MUST be layered through
`docker-compose.override.yaml` and environment variables; the official upstream
`docker-compose.yaml` MUST NOT be forked or edited in place. Any added service,
dependency, or abstraction MUST be justified in the plan.
Rationale: staying close to upstream keeps upgrades cheap and failures
attributable.

## Infrastructure & Security Constraints

- **Pinned version**: the project MUST use Penpot release `2.18.4`. `PENPOT_VERSION`
  MUST be exactly `2.18.4` in `.env.example` and `.env`; floating tags such as
  `2.18` or `latest` MUST NOT be used. The upstream default
  `${PENPOT_VERSION:-2.18}` MUST be overridden so no service can fall back to it.
  All five official images (`penpotapp/frontend`, `backend`, `exporter`,
  `admin-console`, `mcp`) MUST use that same tag. Rationale: all five tags were
  confirmed on Docker Hub with `amd64` and `arm64` manifests, so they run on the
  macOS host, and a mixed-version stack is unsupported.
- **Secrets**: `PENPOT_SECRET_KEY`, database passwords, and the MCP user token
  MUST live only in a git-ignored `.env`. A committed `.env.example` MUST contain
  placeholders only. Secrets MUST NOT appear in code, logs, docs, or commits.
  Postgres keeps the password it was first started with, so `init` MUST refuse to
  create a new `.env` while the real stack's database volume exists, and MUST
  never overwrite an existing `.env`.
- **Network exposure**: published ports MUST bind to `127.0.0.1` by default.
  Exposing a service on other interfaces requires an explicit, documented
  decision. The upstream compose publishes `9001` (frontend) and `8025`
  (Mailpit) on all interfaces, so the override MUST rebind both to `127.0.0.1`
  using the `!override` tag. Compose merges `ports` lists additively, so a plain
  override would leave the original binding in place. The gate is behaviour, not
  a version number: the merged-configuration validator MUST parse the output of
  `docker compose config` and fail if any published port is not bound to
  `127.0.0.1`. A Compose that does not apply `!override` is detected that way, and
  the error MUST report the detected Compose version without claiming a minimum
  version.
- **Port availability**: ports MUST be checked before starting the stack. On
  OrbStack a program on the Mac that holds a port does not make `docker compose
  up` fail, so the check MUST NOT rely on Docker's own error alone.
- **Docker runtime neutrality**: the setup MUST work on any runtime that provides
  `docker compose` (Docker Desktop, OrbStack, and similar). Messages, documents,
  and code MUST NOT assume one runtime, and processes belonging to the runtime
  MUST NOT be reported as port conflicts.
- **Health checks**: every service MUST define a healthcheck.
- **Persistence**: Postgres data and uploaded assets MUST use named volumes.

## Penpot & MCP Integration Rules

- **Authoritative source**: the Penpot repository at tag `2.18.4`
  (`https://github.com/penpot/penpot/tree/2.18.4`) is the source of truth for
  images, environment variables, flags, and ports. Every such claim MUST cite a
  file in that tag (for example `docker/images/docker-compose.yaml` or
  `mcp/README.md`). `help.penpot.app` is secondary and MUST NOT override the
  tag when they disagree. A claim with no citation MUST be marked `[unverified]`
  until confirmed by a real smoke test against the running stack.
- **Version upgrades**: changing the pinned version MUST be a deliberate,
  separate change. It MUST re-read the new tag's `docker/images/docker-compose.yaml`
  and `mcp/README.md`, update the affected docs and overrides, bump this
  constitution, and re-run the smoke test before it is considered done.
- **Browser origin**: the Penpot UI calls its API at `PENPOT_PUBLIC_URI`, and the
  browser blocks any other origin (CORS). `PENPOT_PUBLIC_URI` of the frontend,
  backend, exporter, and admin console MUST equal
  `http://localhost:<published frontend port>`. The override MUST make it follow
  `PENPOT_HTTP_PORT`, `bin/penpot check` MUST enforce it, and users and
  documents MUST tell people to open exactly that address.
- **MCP mode**: MCP MUST be enabled through the `enable-mcp` flag in
  `PENPOT_FLAGS`. The remote endpoint served by the self-hosted instance
  (`/mcp/stream`) is the preferred mode. The local `@penpot/mcp` server MUST NOT
  be used unless it is itself containerized and the deviation is documented.
- **Operational caveats MUST be documented**: each user has a single MCP key, and
  regenerating it immediately revokes the previous one; and an open Penpot
  browser tab with the plugin connected is required during every agent session.
- **Smoke test**: a repeatable containerized smoke test MUST verify that the
  stack starts healthy and that the MCP endpoint answers, before the integration
  is declared working. Checks that bypass the browser (for example `curl`) cannot
  prove the UI works, so a real browser test MUST also be run before a change to
  addresses, ports, or origins is declared working.

## Governance

This constitution supersedes all other practices in this repository. Amendments
require a written proposal, an updated Sync Impact Report, and a version bump:
MAJOR for removed or redefined principles, MINOR for added or materially
expanded guidance, PATCH for clarifications. Every plan, task list, and review
MUST include a check against these principles, and any complexity violation MUST
be recorded with its justification. Runtime guidance for agents lives in
`CLAUDE.md` when present.

**Version**: 1.2.0 | **Ratified**: 2026-10-25 | **Last Amended**: 2026-10-25
