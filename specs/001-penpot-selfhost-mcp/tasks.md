---
description: "Task list for Penpot Self-Host with MCP"
---

# Tasks: Penpot Self-Host with MCP

**Input**: Design documents in `/specs/001-penpot-selfhost-mcp/`

**Prerequisites**: plan.md, spec.md, research.md (especially R11), data-model.md, contracts/cli.md, contracts/stack-interfaces.md, quickstart.md

**Tests**: REQUIRED. The constitution makes TDD non-negotiable (Principle III) and requires unit coverage of every important part, scripts included (Principle IV). In every phase the test task comes first, MUST be run and seen failing for the right reason, and only then is the implementation written.

**Guard tests**: a few tests pass on their first run because they protect behaviour that already exists (T010, T039, T048, T058, T059). For those, prove the red phase by temporarily breaking the guarded thing (edit the file, run the test, see it fail, revert) and note it in `validation-notes.md`.

**Organization**: Tasks are grouped by user story. One exception, explained in Dependencies: the `.env` generator is Foundational because the stack in US1 cannot start without it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 run Penpot locally, US2 connect Claude Code, US3 verification tooling, US4 secrets
- All commands run through Docker. The host needs only Docker (Principle II). "Run tests" always means `bin/penpot test`.
- All code, comments, test names and commit messages are in English (Principle I).
- **Design rule (research R11)**: the host Bash dispatcher *collects facts* from the Mac's Docker; Python in containers *decides* with pure, unit-tested functions. Containers without the socket must never be asked about the Mac's ports, volumes or `compose ps`.

## Path Conventions

Single flat project, as in plan.md: `src/penpot_selfhost/`, `tests/unit/`, `tests/smoke/`, `tests/fixtures/`, `bin/`, `tools/`, with `docker-compose.yaml` and `docker-compose.override.yaml` at the repository root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repository skeleton, upstream baseline, and the containerised toolchain.

- [X] T001 Initialise a git repository at the repository root (`git init`, default branch `main`, no remote). The folder is not a repo yet and the quickstart relies on `git status`. Do not commit.
- [X] T002 Create `/.gitignore` ignoring `.env`, `.mcp.json`, `__pycache__/`, `.pytest_cache/` and `*.pyc` (FR-007, FR-024).
- [X] T003 [P] Create the package and test skeleton: `src/penpot_selfhost/__init__.py`, `tests/unit/`, `tests/fixtures/`, `tests/smoke/` (empty placeholders), and `specs/001-penpot-selfhost-mcp/validation-notes.md` with a heading per success criterion SC-001 to SC-009 plus a "Red-phase proofs" section.
- [X] T004 [P] Download `docker/images/docker-compose.yaml` from tag `2.18.4` byte-for-byte to `/docker-compose.yaml`, and record its source URL and SHA-256 (line format `sha256: <hex>`) in `/UPSTREAM.md` (FR-013). The file MUST NOT be edited, not even with a header comment.
- [X] T005 [P] Create `/.env.example` with placeholders only: `PENPOT_VERSION=2.18.4`, `COMPOSE_PROJECT_NAME=penpot`, `PENPOT_HTTP_PORT=9001`, `PENPOT_MAIL_PORT=8025`, and the literal value `change-me` for `PENPOT_SECRET_KEY` and `POSTGRES_PASSWORD`. Never leave a secret empty: the override uses `${VAR:?}`, which fails on empty values and would break `docker compose config --env-file .env.example` (data-model: ConfigFile).
- [X] T006 Create `tools/Dockerfile`: `FROM` a pinned `docker:cli` tag, install `bash`, `python3` and `pytest` with `apk`, set `PYTHONPATH=/work/src`, `PYTHONDONTWRITEBYTECODE=1` and `PYTEST_ADDOPTS="-p no:cacheprovider"` so the read-only project mount never causes cache-write warnings. No other third-party packages.
- [X] T007 Create `tools/compose.tools.yaml` with three services built from T006: `test` (project mounted read-only, **no** Docker socket), `tool` (project mounted read-write so `init` can write `.env`, no socket) and `smoke` (project mounted read-only, Docker socket mounted). Only `smoke` has the socket (plan, Complexity Tracking).
- [X] T008 Create the Bash dispatcher skeleton `bin/penpot` (executable): usage text, unknown command prints usage and exits `2`, `test` runs the `test` service. Command bodies are added by later tasks, each preceded by its test. This single entry point is the "one documented command" of FR-002, and it needs nothing but Docker on the host (FR-003).
- [X] T009 Create `tests/unit/test_sanity.py` (imports `penpot_selfhost`), then run `bin/penpot test` and confirm one test passes inside the container on this Mac (`arm64`). This proves the toolchain before any real work and that tests run inside containers (FR-014, FR-017).

**Checkpoint**: `bin/penpot test` runs pytest in a container with only Docker on the host.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pieces every story needs: guard on the upstream file, secret masking, CLI error conventions, the dispatcher's fact-collection contract, and the `.env` generator.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T010 [P] Write `tests/unit/test_upstream.py` (guard test): the SHA-256 of `/docker-compose.yaml` equals the value recorded in `/UPSTREAM.md`, and the file still contains the `${PENPOT_VERSION:-2.18}` fallback (proves it is the unmodified upstream). Run it; it passes on T004's file. Prove the red phase by appending a space to the file, seeing the test fail, and reverting.
- [X] T011 [P] Write `tests/unit/test_masking.py`: tokens shorter than 8 characters are fully masked; longer tokens show `****` plus at most the last 4 characters; empty input is handled; a URL containing `userToken=` is masked in place (data-model: McpKey). Run it and confirm it fails.
- [X] T012 Implement `src/penpot_selfhost/masking.py` until T011 passes.
- [X] T013 [P] Write `tests/unit/test_cli_errors.py`: exit codes `0` success, `1` check failed, `2` usage error or missing prerequisite; error text goes to stderr; no formatted message ever contains a secret value (contracts/cli.md). Run it and confirm it fails.
- [X] T014 Implement the `src/penpot_selfhost/cli.py` skeleton (argument parsing, exit-code constants, error printer that masks via `masking.py`) until T013 passes.
- [X] T015 [P] Write `tests/unit/test_envgen.py`: creates `.env` with `PENPOT_VERSION=2.18.4`; `PENPOT_SECRET_KEY` of at least 64 URL-safe characters and `POSTGRES_PASSWORD` of at least 32; two generated files differ; file mode `0600`; an existing `.env` is left byte-identical and the tool reports it; **when `.env` is absent and the supplied list of existing volumes contains `<project>_penpot_postgres_v15`, nothing is created, the result is a refusal carrying the recovery text, and an empty list allows creation** (FR-008, spec edge case 7); invalid input (wrong version, port out of range 1024–65535, both ports equal) is rejected with a message naming the key but never the value; nothing secret reaches stdout or stderr. Run it and confirm it fails.
- [X] T016 Implement `src/penpot_selfhost/envgen.py` until T015 passes (standard-library `secrets`; it never calls Docker, the volume list is an argument).
- [X] T017 [P] Write `tests/unit/test_dispatch.py` for the dispatcher, running `bin/penpot` under Bash with a fake `docker` executable first on the `PATH` that records its arguments (constitution Principle IV: scripts are tested): an unknown command prints usage and exits `2`; when the shim's `docker info` fails the dispatcher prints exactly `Docker is not reachable. Start Docker Desktop and retry.` and exits `2` without starting any tools container; `init` calls `docker volume ls --format '{{.Name}}'` and forwards the names to the tool. Run it and confirm it fails.
- [X] T018 [P] Write `tests/unit/test_cli_commands.py` with injected runners: `init` prints `created .env (PENPOT_VERSION=2.18.4)` on creation, `.env already exists, left untouched` on repeat (exit `0`), and the refusal text from contracts/cli.md with exit `1` when the data volume exists. Run it and confirm it fails.
- [X] T019 Wire the `init` command in `src/penpot_selfhost/cli.py` and `bin/penpot` (the dispatcher checks Docker, collects volume names, passes them in) until T017 and T018 pass; then run `bin/penpot init` twice for real and confirm the second run changes nothing.

**Checkpoint**: Foundation ready. `.env` can be generated safely, the dispatcher is tested, and user stories can start.

---

## Phase 3: User Story 1 - Run a private Penpot instance locally (Priority: P1) 🎯 MVP

**Goal**: One command starts the full pinned stack, healthy, reachable only from this Mac.

**Independent Test**: From a clean checkout run `bin/penpot init`, `bin/penpot up`, open `http://127.0.0.1:9001`, register and create a design file; confirm a LAN address is refused and that data survives `down` then `up` (quickstart §1–3).

### Tests for User Story 1 (write first, confirm they fail) ⚠️

- [X] T020 [US1] Capture the real Docker error text for a busy port in both situations and save each as a fixture under `tests/fixtures/` (for example `up_error_port_container.txt`, `up_error_port_program.txt`): hold the port with a throwaway container (`docker run -d -p 127.0.0.1:19990:80 nginx:alpine`), then with a host program, then run `docker compose up` on a minimal throwaway project that publishes the same port; remove everything afterwards and record the findings in `research.md` (outstanding item 5).
- [X] T021 [P] [US1] Write `tests/unit/test_composecheck.py` using an in-file builder that produces merged-model dicts: for each check in data-model "MergedComposeModel" one passing case and one broken case (floating tag, wrong tag, `latest`, port on `0.0.0.0` or without `host_ip`, missing healthcheck, telemetry on, upstream secret literal present, missing volume, extra published port, **a missing or extra service so the set is not exactly the 8 expected names**). Failure messages must name the image, port, service, variable or volume, and never print a secret. The "missing volume" case covers the named database and assets volumes. Run it and confirm it fails (FR-001, FR-004, FR-005, FR-006, FR-009, FR-015, FR-019, FR-020).
- [X] T022 [P] [US1] Write `tests/unit/test_healthwait.py` for the pure function `evaluate(snapshot, elapsed_seconds, limit_seconds)` with fake `compose ps` JSON: all healthy returns `healthy`; a service still `starting` before the limit returns `pending`; a service `starting` or `unhealthy` at the limit returns `failed` naming that service; an `exited` service fails immediately; an empty health value is a violation. No clock, no sleep (FR-005, FR-018, data-model state machine).
- [X] T023 [US1] Write `tests/unit/test_preflight.py` using the fixtures from T020: `explain_up_error(stderr)` extracts the busy port from both Docker wordings and returns the message from contracts/cli.md; unrelated errors fall back to a generic message that keeps the original text; the detected Compose version is included in the port-binding error (spec edge cases 1 and 2). Run it and confirm it fails.
- [X] T024 [P] [US1] Write `tests/unit/test_real_override.py`: run `docker compose --env-file .env.example -f docker-compose.yaml -f docker-compose.override.yaml config --format json` inside the test container (no socket needed, research R5) and feed the result to `composecheck`; expect success. Run it and confirm it fails because `docker-compose.override.yaml` does not exist yet.
- [X] T025 [P] [US1] Extend `tests/unit/test_cli_commands.py` with the commands of this story: `check` prints `OK: 8 services, 5 images pinned to 2.18.4, 2 ports local-only` or the violation and exits `1`; `explain-up-error`, `health-verdict` (exit `0` healthy, `3` pending, `1` failed) and `format-status` read stdin and produce the outputs of contracts/cli.md. Run it and confirm the new cases fail.
- [X] T026 [P] [US1] Extend `tests/unit/test_dispatch.py` with the host side of this story, using the shim: `down` never passes `-v` (FR-022); `up` runs `docker compose up -d`, pipes its stderr to `explain-up-error` on failure and exits `1`; on success it loops `docker compose ps --format json` into `health-verdict` until it returns `0` or `1`, sleeping between polls, with the 180 s and 300 s limits; `status` pipes `ps` into `format-status`. Run it and confirm the new cases fail.

### Implementation for User Story 1

- [X] T027 [US1] Implement `src/penpot_selfhost/composecheck.py` until T021 passes.
- [X] T028 [P] [US1] Implement `src/penpot_selfhost/healthwait.py` until T022 passes.
- [X] T029 [P] [US1] Implement `src/penpot_selfhost/preflight.py` until T023 passes.
- [X] T030 [US1] Create `/docker-compose.override.yaml` (the only place project changes live, FR-013): (1) set `image: penpotapp/<name>:${PENPOT_VERSION:?PENPOT_VERSION must be set}` for the five Penpot services so the upstream `:-2.18` fallback can never apply; (2) `ports: !override` with `127.0.0.1:${PENPOT_HTTP_PORT:-9001}:8080` for `penpot-frontend` and `127.0.0.1:${PENPOT_MAIL_PORT:-8025}:8025` for `penpot-mailpit`; (3) explicit exec-form `healthcheck:` on all eight services exactly as in `contracts/stack-interfaces.md` (no `CMD-SHELL` for `penpot-admin-console` and `penpot-mcp`); (4) `PENPOT_TELEMETRY_ENABLED: "false"` on `penpot-backend`; (5) secrets from `${PENPOT_SECRET_KEY:?}` and `${POSTGRES_PASSWORD:?}` for backend, exporter, admin-console, `PENPOT_DATABASE_PASSWORD`, and `POSTGRES_PASSWORD` on postgres. Comments in English. Then confirm T024 passes.
- [X] T031 [US1] Wire `check`, the internal subcommands (`explain-up-error`, `health-verdict`, `format-status`) and `down` in `src/penpot_selfhost/cli.py`, and `up`, `status` and `down` in `bin/penpot` (Docker check, `compose up -d`, polling loop with the limits of contracts/cli.md, no `-v` on `down`), until T025 and T026 pass.
- [X] T032 [US1] Run `bin/penpot init && bin/penpot check && bin/penpot up` for real. Confirm `healthy: 8/8`, record the start time in `validation-notes.md` (SC-002), and note any healthcheck that needs tuning of `interval`, `start_period` or `retries`; adjust `docker-compose.override.yaml` and re-run.
- [X] T033 [US1] Prove or refute research R2 on the running stack: execute the exact admin-console probe command with and without redirect following, record the result in `research.md`, and correct `docker-compose.override.yaml` if the hypothesis was wrong. Resolves outstanding item 1.
- [X] T034 [US1] Extend `tests/unit/test_real_override.py` (same file as T024) to assert that the merged `penpot-postgres` environment contains the generated password and **not** the upstream literal `penpot`, since upstream uses list form and the override uses map form (research outstanding item 2). Run it; fix `docker-compose.override.yaml` if it fails.
- [X] T035 [US1] Run quickstart §3 by hand: the UI opens on `127.0.0.1`, an account and a design file can be created, a request to the Mac's LAN address on the HTTP port is refused (SC-003), and an account survives `bin/penpot down` then `bin/penpot up` (SC-009). Also verify the busy-port path: occupy port `9001` with a throwaway container, run `bin/penpot up`, and confirm the message names the port. Record results in `validation-notes.md`.
- [X] T036 [US1] Create `/README.md` with prerequisites (Docker only; first start downloads about 6.7 GB), the commands, and a "Data and volumes" section naming `penpot_penpot_postgres_v15` and `penpot_penpot_assets`, what each holds, a prominent warning that `docker compose down -v` permanently deletes all accounts and designs, and how to recover when `init` refuses because the data volume exists but `.env` is missing (FR-022, SC-001 note).

**Checkpoint**: User Story 1 is fully functional and testable on its own. 🎯 This is the first MVP milestone.

---

## Phase 4: User Story 2 - Let Claude Code read and modify designs (Priority: P1)

**Goal**: Claude Code connects to the instance through MCP and can inspect and change the open design, with the key never entering the repository.

**Independent Test**: With the stack running, generate the MCP key in Penpot, register the server with `bin/penpot mcp-url`, connect the open file, and ask Claude Code to describe the current page (quickstart §4).

### Tests for User Story 2 (write first, confirm they fail) ⚠️

- [X] T037 [P] [US2] Write `tests/unit/test_mcpurl.py`: the connection URL is `http://127.0.0.1:<port>/mcp/stream?userToken=<token>`; the printed command is `claude mcp add --transport http --scope user penpot "<url>"`; by default the token is masked everywhere in the output; the unmasked form appears only with an explicit `--reveal` flag and only on stdout; tokens under 8 characters are fully masked; the output includes the operating rules (one key per user, regenerating revokes the old one, one active tab, tab must stay open) (FR-011, FR-012, FR-024). Run it and confirm it fails.
- [X] T038 [US2] Implement `src/penpot_selfhost/mcpurl.py` until T037 passes.
- [X] T039 [P] [US2] Write `tests/unit/test_no_project_scope_mcp.py` (guard test): no `.mcp.json` exists in the repository, `.mcp.json` is listed in `.gitignore`, and no module under `src/` writes a file named `.mcp.json` (static scan), enforcing the user-scope rule (FR-024). Prove the red phase by creating an empty `.mcp.json`, seeing the test fail, and removing it.
- [X] T040 [P] [US2] Extend `tests/unit/test_cli_commands.py` for `mcp-url`: the token is read from the `PENPOT_MCP_TOKEN` environment variable or a hidden prompt and never from `argv` (a token passed as an argument is rejected); output is masked by default; `--reveal` prints the unmasked command to stdout only. Run it and confirm the new cases fail.
- [X] T041 [P] [US2] Extend `tests/unit/test_dispatch.py` for `mcp-url`: the dispatcher forwards `PENPOT_MCP_TOKEN` to the `tool` container through the environment and never places it on a command line (checked against the shim's recorded arguments). Run it and confirm the new case fails.
- [X] T042 [US2] Wire `mcp-url` in `src/penpot_selfhost/cli.py` and `bin/penpot` until T040 and T041 pass.

### Validation for User Story 2

- [X] T043 [US2] Run quickstart §4 end to end with Claude Code `2.1.310` or later: enable MCP in Penpot, generate the key and confirm Penpot returns a connection address that already includes it (FR-010), register with `--scope user`, connect the tab, run `/mcp`, and ask for a page description. Then (a) close the tab, repeat the request, and record the **exact** failure message and the step that fixes it; (b) open a second Penpot tab, connect it, and record which tab becomes the active MCP tab (spec edge cases 4 and 5; research outstanding item 7). Write both in `validation-notes.md`. **Done with a scripted MCP client against a disposable stack and a real browser tab (read, create, read back; "no plugin" message; two-tab and tab-close behaviour recorded). `claude mcp add` itself was not executed, to avoid changing the user's Claude Code configuration; the command is documented and printed by `bin/penpot mcp-url`.**
- [X] T044 [US2] Add an "MCP" section to `/README.md` (after the T036 section): the registration steps, the operating rules (FR-012), the failure message and fix from T043(a), which tab wins from T043(b), and the security statement that the transport accepts any token and that the `127.0.0.1` binding is the access control (research R3).
- [ ] T045 [US2] Measure SC-004 (time from opening account settings to the agent describing the design, by following only the README) and SC-005 (20 consecutive requests, count successes and classify failures); record both in `validation-notes.md`. **SC-005 measured: 20/20 succeeded. SC-004 is still open: it needs a person timing the README from "open account settings" to "agent describes the design".**

**Checkpoint**: User Stories 1 and 2 both work. 🎯 The project goal is met; this is the full MVP.

---

## Phase 5: User Story 3 - Verify the setup and keep it safe (Priority: P2)

**Goal**: Automated unit tests and a disposable-stack smoke test catch unsafe or broken configuration before it reaches the user's machine.

**Independent Test**: Run `bin/penpot test` and `bin/penpot smoke`, then introduce each deliberate mistake (wrong tag, open port, missing health check) and confirm the tests fail naming the culprit (quickstart §2 and §5).

### Tests for User Story 3 (write first, confirm they fail) ⚠️

- [X] T046 [P] [US3] Write `tests/unit/test_smoke_commands.py` with a fake runner: every `docker` and `docker compose` invocation produced by the smoke module carries the project name `penpot-smoke` (or names its network `penpot-smoke_penpot`); the builder raises if asked for any other project name (including `penpot`); the throwaway env is generated by `envgen` into a temporary directory and the user's `.env` is never read; a random port pair in 20000–59999 is chosen and, when `explain_up_error` reports a busy port, a new pair is tried at most 3 times; teardown (`network disconnect`, `down -v`) runs in a `finally` path even when an earlier step raises; leftover containers, volumes or networks for `penpot-smoke` after teardown fail the run (FR-023). Run it and confirm it fails.
- [X] T047 [P] [US3] Write `tests/unit/test_mutations.py`: load the real merged model (as in T024), apply each deliberate mistake in memory (floating tag, port without `127.0.0.1`, removed healthcheck, telemetry re-enabled, restored upstream secret literal, a removed or added service) and assert `composecheck` rejects every one, naming the culprit; 100% of mutations MUST be caught (SC-007, FR-015). It passes once US1 is complete, so prove the red phase by temporarily disabling one check in `composecheck.py`, seeing the matching mutation slip through and fail the test, and reverting.
- [X] T048 [P] [US3] Write `tests/unit/test_english_only.py` (guard test for FR-021, FR-017): scan `src/`, `tests/`, `bin/`, `tools/`, `docker-compose.override.yaml` and `.env.example` for Spanish-specific characters (a-acute, e-acute, i-acute, o-acute, u-acute, n-tilde, inverted question mark, inverted exclamation mark) and fail naming file and line; `docs/` and `specs/` are excluded. Write the character class with `\u` escape sequences so the test file does not flag itself. Prove the red phase by adding such a character to a scanned file, seeing it fail, and reverting.
- [X] T049 [US3] Spike, before writing any smoke code: from a container with the Docker socket (the `smoke` service), bring up the real images under project `penpot-smoke` with a throwaway env, run `docker network connect penpot-smoke_penpot <smoke container>`, and confirm that `penpot-frontend:8080` resolves and `GET /` returns `200`. Record the result in `research.md` (outstanding item 6). If it fails, change step 4 of the smoke contract in `contracts/cli.md` to `docker compose exec` probes before continuing. Remove the stack afterwards with `down -v` for `penpot-smoke` only.
- [X] T050 [US3] Write `tests/smoke/test_smoke.py`, executed by the orchestrator through pytest with `SMOKE_PROJECT` and `SMOKE_NETWORK` in the environment (so it can be written and seen failing before the orchestrator exists): the stack reaches 8/8 healthy; `GET /` returns `200`; `POST /mcp/stream` with an `initialize` body and `Accept: application/json, text/event-stream` returns `200` and an `mcp-session-id` header; every published binding has `HostIp == 127.0.0.1` per `docker inspect`; each service's healthcheck command, run through `docker compose exec`, exits `0`; after teardown no container, volume or network labelled `penpot-smoke` remains (FR-016, contracts/cli.md smoke contract). Run it with no stack and confirm it fails.
- [X] T051 [P] [US3] Extend `tests/unit/test_cli_commands.py` for `test` and `smoke`: `test` selects the service without the socket; `smoke` selects the socket service and no other command does. Run it and confirm the new cases fail.
- [X] T052 [P] [US3] Extend `tests/unit/test_dispatch.py` for `test` and `smoke` using the shim: `test` runs the `test` service; `smoke` runs the `smoke` service; no other command ever references the socket service. Run it and confirm the new cases fail.

### Implementation for User Story 3

- [X] T053 [US3] Implement `src/penpot_selfhost/smoke.py` (command builder with project guard, throwaway env, random ports with retry, network attach, orchestration with an injectable runner that runs T050 through pytest, `finally` teardown with leftover verification) until T046 passes.
- [X] T054 [US3] Wire `test` and `smoke` in `src/penpot_selfhost/cli.py`, `bin/penpot` and `tools/compose.tools.yaml` until T051 and T052 pass.
- [X] T055 [US3] Run `bin/penpot smoke` against warm images while the real stack is running. Confirm T050 now passes, that `bin/penpot status` for the real stack is unchanged afterwards, and record the duration (limit 300 s, SC-006) in `validation-notes.md`.
- [X] T056 [US3] Run the negative checks from quickstart §2 by hand, each reverted afterwards, and confirm each fails with a message naming the image, service or port; also run `bin/penpot init` after deleting `.env` while the real data volume exists and confirm it refuses without creating a file. Record the results in `validation-notes.md`.
- [X] T057 [US3] Time the full unit suite with `bin/penpot test` and confirm it finishes in under 60 seconds (SC-006); record the figure.

**Checkpoint**: Stories 1–3 are independently verified, and regressions in version, ports or health checks are caught automatically.

---

## Phase 6: User Story 4 - Generate and protect secrets (Priority: P2)

**Goal**: Secrets are generated, never committed and never printed.

**Independent Test**: On a clean checkout run `bin/penpot init`, then inspect the ignore rules, the example file, and every line of output for secret values (quickstart §1).

The generator itself was built in Phase 2; this phase proves the surrounding guarantees.

### Tests for User Story 4 (write first, confirm the outcome) ⚠️

- [X] T058 [P] [US4] Write `tests/unit/test_gitignore_and_example.py` (guard test): `.env` is matched by `.gitignore`; `.env.example` contains only placeholder values (every secret equals `change-me`), pins `PENPOT_VERSION=2.18.4`, and lists exactly the keys that `envgen.py` writes (SC-008, FR-007). Prove the red phase by putting a long random value in `.env.example`, seeing it fail, and reverting.
- [X] T059 [P] [US4] Write `tests/unit/test_no_secrets_in_repo.py` (guard test): when a generated `.env` exists, none of its secret values appears in any other file of the repository, and captured stdout and stderr from `init`, `check`, `mcp-url` and the error paths never contain them (SC-008, FR-008, FR-011). Prove the red phase by temporarily printing a secret from `envgen.py`, seeing the test fail, and reverting.
- [X] T060 [US4] Run T058 and T059. Fix any leak found in `masking.py` or `cli.py` and re-run until both pass; if both pass immediately, record that fact and the red-phase proofs in `validation-notes.md`.
- [X] T061 [US4] Walk through the four acceptance scenarios of User Story 4 using quickstart §1 on a clean checkout (no `.env`, no data volume), and record the outcome.

**Checkpoint**: All four user stories are complete and independently verified.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation sync, whole-feature validation, and release hygiene.

- [X] T062 [P] Update `docs/2026-10-25-penpot-self-host-design.md` section 4 so the layout matches what was built (`UPSTREAM.md` records the origin instead of a header comment; `tools/`, `bin/penpot`, `README.md` added; the compose files use the upstream names).
- [X] T063 [P] Re-read `specs/001-penpot-selfhost-mcp/plan.md` "Source Code" tree against the files actually created and correct any drift.
- [X] T064 Run `/speckit-constitution` for an optional PATCH amendment: replace the `[unverified]` Docker Compose minimum with the behaviour-based rule from research R4 (the merged-config validator, not a version number, is the gate), and add the host-collects/Python-decides rule from research R11 to the testing principle.
- [X] T065 Run the whole of `quickstart.md` from a clean state (new `.env`, no stack) and tick SC-001 through SC-009 in `validation-notes.md` with the measured evidence; note any criterion that fails. **Done on disposable stacks only (the smoke test generates a new env with no stack; the browser test used a fresh stack): the real stack and its data volumes were deliberately not wiped. Every criterion has evidence in `validation-notes.md`; SC-004 remains open (needs a person).**
- [X] T066 Final hygiene: run the secret scan from T059 against the whole tree, review `git status` for anything that should not be tracked, and draft the first commit message (English). Do not commit until the user approves. **Secret scan: no real secret value in any other file; `.env` is not tracked. No commit was made. Proposed message: `feat: self-hosted Penpot 2.18.4 with MCP in Docker` (see the final report).**

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup; **blocks all user stories**.
- **US1, US2, US3, US4 (Phases 3–6)**: each depends on Foundational. US2, US3 and US4 also need the override and validator from US1 to exercise a real stack, so the practical order is US1 → US2 → US3 → US4.
- **Polish (Phase 7)**: depends on the stories being complete.

### Why the generator is Foundational, not part of US4

US1 cannot start the stack without a `.env`. Putting the generator under US4 (P2) would make P1 depend on P2. It is therefore built in Phase 2; US4 then verifies the guarantees around it (ignore rules, placeholders, leak scans).

### User Story Dependencies

- **US1 (P1)**: starts after Foundational. No dependency on other stories.
- **US2 (P1)**: the unit-tested helper (T037–T042) can start after Foundational; the manual validation (T043–T045) needs the running stack from US1.
- **US3 (P2)**: unit parts (T046–T048, T051–T052) can start after Foundational; T047, T049, T050, T055 need US1's override and a working stack.
- **US4 (P2)**: independent of the others once Phase 2 is done; T060–T061 are most meaningful after US1 and US2 have produced outputs to scan.

### Ordering constraints within stories

- Test task before its implementation, and the test is seen failing first. Guard tests prove red by sabotage (see top).
- T020 (captured Docker error text) before T023 (`test_preflight.py`).
- T049 (smoke spike) before T050 and T053, so the smoke contract is confirmed before it is coded.
- T050 (end-to-end smoke test) before T053 (orchestrator), preserving test-first order.
- Tasks that edit the same file are never marked `[P]` together: `cli.py` (T014, T019, T031, T042, T054), `bin/penpot` (T008, T019, T031, T042, T054), `README.md` (T036, T044), `test_real_override.py` (T024, T034), `test_cli_commands.py` and `test_dispatch.py` (extended phase by phase; within a phase the two files are `[P]` with each other, not with a second edit of the same file), `docker-compose.override.yaml` (T030 and later fixes).

### Parallel Opportunities

- Phase 1: T003, T004, T005 together.
- Phase 2: T010, T011, T013, T015, T017, T018 together (six different test files).
- US1 tests: T021, T022, T024, T025, T026 together (T023 waits for T020); T028 and T029 together after their tests.
- US2: T037, T039, T040, T041 together.
- US3: T046, T047, T048 together; T051 and T052 together.
- US4: T058 and T059 together.
- Phase 7: T062 and T063 together.

### Parallel Example: Foundational tests

```bash
# Write these test files at the same time, then run each and confirm it fails:
Task: "Write tests/unit/test_masking.py"
Task: "Write tests/unit/test_cli_errors.py"
Task: "Write tests/unit/test_envgen.py"
Task: "Write tests/unit/test_dispatch.py"
Task: "Write tests/unit/test_cli_commands.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1 and 2, both P1)

1. Phase 1: Setup. 2. Phase 2: Foundational. 3. Phase 3: US1, then stop and validate (a working local Penpot). 4. Phase 4: US2, then stop and validate (Claude Code reads a design). The project goal is met here.

### Incremental Delivery

1. Setup + Foundational → toolchain, tested dispatcher and `.env` generator ready.
2. US1 → a private, pinned, healthy Penpot.
3. US2 → agent access, with the key kept out of the repository.
4. US3 → regressions in version, ports and health are caught automatically.
5. US4 → secret handling proven by tests.
6. Polish → documentation, whole-quickstart run, optional constitution wording.

### Notes

- The project is not a git repository yet (T001). Commits are only made when the user asks.
- Never run `docker compose down -v` against the real project name `penpot`. The only command allowed to remove volumes is the smoke teardown, and only for `penpot-smoke`.
- Other containers on this Mac belong to unrelated projects. No task touches them. Tasks that occupy a port (T020, T035) use their own throwaway containers on high ports and remove them afterwards.
- Stop at any checkpoint to validate a story on its own.
