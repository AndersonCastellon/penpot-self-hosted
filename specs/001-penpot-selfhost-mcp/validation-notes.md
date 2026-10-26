# Validation Notes

Measured evidence for the success criteria of [spec.md](spec.md). Filled in while implementing.
Do not record secrets or MCP keys here.

Environment: macOS (arm64), OrbStack as the Docker runtime, Docker Engine 29.4.0, Compose v5.1.2.

## Red-phase proofs

Tests that passed on their first run (guard tests) and how their red phase was demonstrated.

| Test | Sabotage used | Result |
|---|---|---|
| `test_upstream.py` (T010) | appended one space to `docker-compose.yaml` | `test_compose_file_matches_recorded_hash` failed with "docker-compose.yaml was modified"; green again after restoring (sha256 unchanged) |
| `test_no_project_scope_mcp.py` (T039) | created an empty `.mcp.json` in the repository root | `test_there_is_no_project_scoped_mcp_config_file` failed; green after removing it |

Tests whose red phase was the missing module or file (normal TDD): masking, cli errors, envgen, cli commands,
dispatch, composecheck, healthwait, preflight, real override, mcpurl.

## SC-001 Time from checkout to a logged-in session (warm image cache)

Not measured as a whole yet. Parts measured: `bin/penpot init` + `check` under 5 s; `bin/penpot up` reached
`healthy: 8/8 in 11s` with the images already downloaded (18 s wall clock including the script).

## SC-002 All services healthy on a warm start (limit 180 s)

PASS. `bin/penpot up` on the real stack: `healthy: 8/8 in 11s`. Earlier probe on the research stack: `/readyz` 200 in about 15 s.

## SC-003 Published ports reachable from another device

PASS (configuration and live check). `docker compose ps` shows `127.0.0.1:9001->8080` and `127.0.0.1:8025->8025`;
`lsof` shows the runtime listening on `127.0.0.1` only; a request to the Mac's LAN address
(`192.168.0.11:9001`) was refused (connection error, curl exit 7, HTTP code `000`).

## SC-004 Claude Code connection time (limit 10 minutes)

OPEN: needs a person who follows only the README and is timed. What was verified instead is that every step of the
README flow works (see SC-005 and Observations). Claude Code's own `claude mcp add` was not run, so that the user's
personal Claude Code configuration is not changed.

## SC-005 Agent requests, 20 consecutive (at least 19 succeed)

PASS: 20 of 20 `execute_code` calls succeeded with the plugin connected (disposable stack `penpot-e2e`, real browser
tab, scripted MCP client over streamable HTTP). Latency was a few milliseconds per call. Failures: none.
Before the plugin connected, the same call failed with the exact message recorded in Observations.

## SC-006 Unit suite (limit 60 s) and smoke test (limit 300 s)

Unit suite: 252 tests, about 0.6 s of test time (about 1.1 s wall clock including the container start).
Smoke test: `bin/penpot smoke` passed (5 checks) in about 27 s of wall clock, run while the real stack was healthy and
untouched; afterwards 0 containers, 0 volumes and 0 networks were left for `penpot-smoke`.

## SC-007 Deliberate mistakes caught by the tests

PASS for the validator: `test_composecheck.py` applies 28 deliberate mistakes (floating tags, `latest`, wrong
image, open port, missing host IP, extra published port, missing/`NONE`/shell health check, telemetry on, upstream
secrets, a wrong public URI, missing volumes, missing or extra services) and every one is detected naming the culprit.
`test_mutations.py` applies the same mistakes to the model rendered from the REAL compose files, and the red phase
was shown by disabling one check. Four more negative checks were run by hand on the real tool (floating tag, removed
health check, port opened to all interfaces, `init` without `.env` while the data volume exists); each failed with a
message naming the culprit and the files were restored byte-identical.

## SC-008 Secret scan of repository, logs and output

PASS for the repository: `test_no_secrets_in_repo.py` finds none of the real secret values in any other file, and the
output of `init`, `check` and `mcp-url` never contains them. Red phase shown three ways (secret copied into another
file, `init` printing the file, long value in `.env.example`). Known additionally: `init` never prints secrets; `mcp-url` masks the key; a usage error no
longer echoes a token passed as an argument (this leak was found by `test_mcp_url_rejects_a_token_passed_as_an_argument`).

## SC-009 Accounts and designs after stop and start

PASS, verified on a disposable stack (`penpot-verify`, removed afterwards; the real stack was not touched):
registered an account through the API, ran `docker compose down` without `-v`, ran `up` again, and the same
credentials logged in (HTTP 200); a wrong password returned 400.

## Observations

### Found during the browser test, and fixed

- **The interface only works when opened at the address in `PENPOT_PUBLIC_URI`.** Upstream hard-codes
  `http://localhost:9001`, and the browser UI calls the API there. Opening `http://127.0.0.1:9001`, or changing
  `PENPOT_HTTP_PORT`, made every call fail with CORS errors and a blank page. Curl checks had not revealed it.
  Fixed: the override makes `PENPOT_PUBLIC_URI` follow `PENPOT_HTTP_PORT`, `composecheck` enforces it (3 new mutations
  plus a real-config test with a custom port), and `bin/penpot up`, the README and the quickstart use `localhost`.
- A key that is generated in **Your account > Integrations** also turns MCP on. The switch is locked (a transparent
  cover opens the "Generate MCP key" dialog) until a key exists.
- After a first login Penpot shows an onboarding questionnaire and a team-choice dialog that block the dashboard.
  Opening a file directly by URL avoids them.

- Docker runtime on this Mac is **OrbStack**, not Docker Desktop. Messages and the README name both.
- With OrbStack a program on the Mac that already holds a port does **not** make `docker compose up` fail
  (`exit 0`, tested with three bind variants). Only a port held by another container produces
  `port is already allocated`. For that reason `bin/penpot up` checks the ports with `lsof` before starting.
- Admin console redirect hypothesis (research R2): proven. The `307` points to `http://localhost:9001/...`.
- Merging env maps works: the upstream list-form `POSTGRES_*` variables are overridden by the map form in the override.
- API note for testing: `prepare-register-profile` requires `fullname` in addition to email and password.

### MCP behaviour observed on 2.18.4 (disposable stack `penpot-e2e`)

- URL shown by Penpot: `http://localhost:<port>/mcp/stream?userToken=<key>`; the key is 354 characters long.
- Tools: `execute_code`, `export_shape`, `high_level_overview`, `penpot_api_info`.
- With the plugin connected: read the page name and shape count; created a 200x120 rectangle named `MCP-rectangle` with
  `execute_code`; read it back; the rectangle appeared on the canvas and in the layers panel.
- With no connected tab, the exact message is: `Tool execution failed: Error: No Penpot instance connected for user token. Please ensure that Penpot is connected and that the MCP client connection is using the correct token.`
- Opening a workspace connects it automatically (hover text on the toolbar MCP button: "MCP connected").
- Two tabs on different files: the first tab kept answering; the second showed "Connect here". Clicking that button
  in an automated session did not move the connection. After the first tab was closed, the second answered.
  After closing all tabs the message above returned.
- The `initialize` handshake is accepted with any token or none (security note in the README).
