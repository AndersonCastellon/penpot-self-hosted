# Penpot self-host with MCP

Penpot **2.18.4** running in Docker on your Mac, reachable only from your own machine, with the
Penpot MCP server enabled so an AI agent such as Claude Code can read and edit your designs.

The official Penpot Compose file is used **unmodified**. Everything this project changes lives in
[`docker-compose.override.yaml`](docker-compose.override.yaml). See [`UPSTREAM.md`](UPSTREAM.md) for the origin
of the official file.

## What you need

- A Docker runtime that provides `docker compose` (Docker Desktop, OrbStack, ...). Nothing else is
  installed on the Mac: Python and the tests run inside containers.
- A browser, and Claude Code if you want the MCP connection.
- The first start downloads about **6.7 GB** of images (the exporter alone is 2.9 GB). Later starts reuse them.

## Quick start

```bash
bin/penpot init     # creates .env with random secrets (never overwrites an existing one)
bin/penpot check    # validates the configuration (version, ports, health checks, telemetry, secrets)
bin/penpot up       # starts everything and waits until all 8 services are healthy
```

Then open **<http://localhost:9001>** and register an account (email verification is disabled, so no
confirmation message is needed).

> **Open `localhost`, not `127.0.0.1`.** The Penpot interface calls its API at `http://localhost:<port>`.
> If you open the same server through another host name (for example `127.0.0.1`), the browser blocks those
> calls and you get a blank page. `bin/penpot check` verifies that the setting follows your port.

| Command | What it does |
|---|---|
| `bin/penpot init` | Create `.env` with generated secrets. Leaves an existing `.env` untouched. |
| `bin/penpot check` | Validate the merged Compose configuration. Fails and names the culprit. |
| `bin/penpot up` | Start the stack and wait until it is healthy (limits: 180 s warm, 300 s first start). |
| `bin/penpot status` | One line per service with its state and health. |
| `bin/penpot down` | Stop the stack. **Volumes are kept**, so your data survives. |
| `bin/penpot mcp-url` | Print the Claude Code registration command with the key masked (`--reveal` shows it). |
| `bin/penpot test` | Run the unit tests (in a container). |
| `bin/penpot smoke` | Run the smoke test on a disposable stack (in a container). |

## Addresses

| URL | What |
|---|---|
| <http://localhost:9001> | Penpot (and the MCP endpoint under `/mcp/stream`) |
| <http://localhost:8025> | Mailpit, a mail catcher. Penpot sends its emails here; nothing leaves your Mac. |

Both ports are published on `127.0.0.1` only, so other devices on your network cannot reach them.
You can change them with `PENPOT_HTTP_PORT` and `PENPOT_MAIL_PORT` in `.env`; the interface address follows
`PENPOT_HTTP_PORT` automatically.

## Connect Claude Code (MCP)

The MCP server is part of the official stack: no extra container, no extra port, and nothing to install on the Mac.
These steps were verified end to end on Penpot 2.18.4 (a client read a design, created a rectangle and read it back).

1. Open <http://localhost:9001> and log in.
2. Go to **Your account > Integrations > MCP Server**. The switch is locked until a key exists: click it, choose an
   expiration (default **Never**) and **Generate MCP key**. Generating the key also turns MCP on.
3. Copy the key from the dialog. **It is shown only once** and cannot be recovered.
4. Register Penpot in Claude Code. The key is read from the environment (or a hidden prompt), never from an argument:

   ```bash
   PENPOT_MCP_TOKEN='<your key>' bin/penpot mcp-url            # prints the command with the key masked
   PENPOT_MCP_TOKEN='<your key>' bin/penpot mcp-url --reveal   # prints the full command to run
   ```

   The command registers the server in **user scope**, so the key is stored in your personal Claude Code
   configuration and never inside this repository:
   `claude mcp add --transport http --scope user penpot "http://127.0.0.1:9001/mcp/stream?userToken=<key>"`
5. Open a design file. When the MCP switch is on, the workspace connects automatically: the toolbar shows an
   **MCP** button with a dot, and hovering it says **MCP connected**. In Claude Code run `/mcp` to see `penpot`.

### What the agent can do

Tools exposed by this server: `execute_code` (runs Penpot Plugin API code on the open file, read and write),
`export_shape`, `high_level_overview` and `penpot_api_info`. Local-file tools (importing an image from a path) are
not available: the server runs in a container and cannot see your files.

### Operating rules

- **One key per user.** Generating a new key revokes the previous one immediately; any client using the old key
  stops working.
- **The Penpot tab must stay open and awake** during agent sessions. If the browser sleeps or unloads it, the
  connection is lost until you reopen the file.
- **One active MCP tab at a time.** Observed on 2.18.4: with two tabs open, the first one keeps the connection and
  the second shows **Connect here** instead of the dot. When the active tab is closed, the other open tab takes over.
  To move the connection by hand use **File > MCP Server > Connect** in the tab you want.
- **No plugin connected** (no open tab, or the MCP switch is off): every tool call fails with this exact message:

  > Tool execution failed: Error: No Penpot instance connected for user token. Please ensure that Penpot is connected
  > and that the MCP client connection is using the correct token.

  Open a design file in Penpot (logged in, MCP enabled) and call the tool again.

### Security note

The MCP endpoint accepts the connection handshake with **any token, or none**. What limits access is that the port is
published on `127.0.0.1` only. The key only pairs an agent with the browser tab whose plugin uses the same key, which
is what lets tool calls reach your open design. Do not publish the port on other interfaces.

## Data and volumes (read this before deleting anything)

Your data lives in two **named Docker volumes**. Their names come from `COMPOSE_PROJECT_NAME=penpot`.

| Volume | Holds |
|---|---|
| `penpot_penpot_postgres_v15` | **Accounts and design files** (they are stored inside the database) |
| `penpot_penpot_assets` | Uploaded images and other assets |

> **Warning:** `docker compose down -v` (or removing these volumes by any other means) **permanently deletes
> all accounts and designs**. There is no automatic backup in this version. `bin/penpot down` never
> passes `-v`.

Why not project folders? The designs live inside Postgres, and committing a running database's binary
files to git is unsafe, so named volumes are used.

### `.env` is missing but the data still exists

Postgres remembers the password it was first started with. If you delete `.env` and generate a new one,
the backend could no longer open your data. For that reason `bin/penpot init` **refuses** to create a new `.env`
while the volume `penpot_penpot_postgres_v15` exists. Restore your previous `.env`, or, only if you accept
losing everything, remove the volumes on purpose.

## If a port is busy

`bin/penpot up` checks the two ports before starting. If a program on your Mac holds one of them, it stops and
tells you which one. Set another port in `.env` (`PENPOT_HTTP_PORT` or `PENPOT_MAIL_PORT`) or stop that program.
A port held by another container is reported from Docker's own error.

## Secrets

`.env` holds the only secrets (`PENPOT_SECRET_KEY` and `POSTGRES_PASSWORD`). It is created with mode `0600`,
ignored by git, and never printed. `.env.example` has placeholders only.
