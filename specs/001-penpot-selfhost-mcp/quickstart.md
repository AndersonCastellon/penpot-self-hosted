# Quickstart: validate Penpot Self-Host with MCP

**Spec**: [spec.md](spec.md) | Contracts: [contracts/cli.md](contracts/cli.md),
[contracts/stack-interfaces.md](contracts/stack-interfaces.md)

A validation guide, not an implementation. Every command below is defined in the CLI contract.
Prerequisite: Docker Desktop running on the Mac, a browser, and Claude Code. Nothing else.

> First start downloads about **6.7 GB** of images (research R7a). Timing figures in the spec
> assume the images are already cached.

## 1. Create the configuration (User Story 4)

```bash
bin/penpot init          # creates .env with generated secrets, PENPOT_VERSION=2.18.4
bin/penpot init          # second run: must say ".env already exists, left untouched"
git status --short       # .env must NOT appear; .env.example may
```

Expected: `.env` exists; no secret printed; second run changes nothing.

## 2. Run the checks (User Stories 3 and 4)

```bash
bin/penpot test          # unit tests, in a container, no Docker socket
bin/penpot check         # merged-config validator
```

Expected: all green; `check` prints `OK: 8 services, 5 images pinned to 2.18.4, 2 ports local-only`.

Negative checks (each MUST fail with a message naming the culprit, then be reverted):
1. Set `PENPOT_VERSION=2.18` in `.env` → `check` names the image and the tag.
2. Remove one `healthcheck:` block from the override → `check` names the service.
3. Replace `127.0.0.1:` with nothing in a port binding → `check` names the port.
4. After the stack has run once, move `.env` aside and run `bin/penpot init` → it MUST refuse, create
   nothing, and explain how to recover (the data volume still exists). Restore `.env` afterwards.

## 3. Start Penpot (User Story 1)

```bash
bin/penpot up
bin/penpot status        # 8 services healthy
```

Expected: `healthy: 8/8` within the documented limit (SC-002); `http://localhost:9001` opens
Penpot (use `localhost`: the UI only works at the address in `PENPOT_PUBLIC_URI`, research R12). Register an account (email verification is disabled), create a design file.

Local-only check:
```bash
docker compose ps --format '{{.Service}} {{.Ports}}'   # only frontend and mailpit show 127.0.0.1:...  (OrbStack and Docker Desktop alike)
curl -s -o /dev/null -w '%{http_code}\n' http://<mac-lan-ip>:9001   # must fail to connect
```

Persistence check (SC-009): `bin/penpot down`, `bin/penpot up`, log in; the account and file are still there.
Never run `docker compose down -v` here: it deletes the volumes (FR-022).

## 4. Connect Claude Code (User Story 2)

1. In Penpot: **Your account → Integrations → MCP Server**, enable it, generate the key (shown once).
2. Copy the server URL, then run:
   ```bash
   PENPOT_MCP_TOKEN='<paste key>' bin/penpot mcp-url
   ```
   It prints the registration command with the token masked. Run the unmasked command it describes
   with `--scope user` (token stays out of the repository, FR-024).
3. Open a design file and choose **File → MCP Server → Connect**. Keep that tab open and awake.
4. In Claude Code run `/mcp`; `penpot` must be listed as connected. Ask: "Describe the current Penpot page."

Expected: an accurate description of the open file (SC-004).

Failure scenarios (observed, then documented in the README; they are upstream behaviour):
1. Close the Penpot tab and repeat the request. The call fails (User Story 2, scenario 4); record the
   exact message and the step that fixes it.
2. Open a second Penpot tab and connect it; record which tab becomes the active MCP tab (spec edge case 5).

## 5. Smoke test on a disposable stack (FR-016, FR-023)

```bash
bin/penpot smoke
docker ps -a --filter label=com.docker.compose.project=penpot-smoke -q | wc -l   # 0
docker volume ls --filter label=com.docker.compose.project=penpot-smoke -q | wc -l  # 0
```

Expected: `smoke OK`; the real stack and its volumes are untouched (`bin/penpot status` unchanged).

## Pass criteria

All steps above succeed, every negative check fails as described, and the success criteria
SC-001 to SC-009 in the spec are met (SC-001 measured from a warm image cache).
