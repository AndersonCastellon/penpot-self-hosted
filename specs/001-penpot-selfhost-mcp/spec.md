# Feature Specification: Penpot Self-Host with MCP

**Feature Branch**: `001-penpot-selfhost-mcp`

**Created**: 2026-10-25

**Status**: Draft

**Input**: User description: "Self-hosted Penpot 2.18.4 on Docker for a macOS host, with the MCP server enabled so AI agents (Claude Code) can read and modify designs. Source of truth: docs/2026-10-25-penpot-self-host-design.md and the Penpot repository at tag 2.18.4."

## Clarifications

### Session 2026-10-25

- Q: Should Penpot's anonymous telemetry be disabled in this installation? → A: Yes, disable it; the override sets it to `false` and a test verifies it.
- Q: Which optional services of the official Compose file should be kept: the mail catcher and the administration console? → A: Keep both; the mail catcher's port is local-only and each has a health check.
- Q: Should backup and restore be included in this version? → A: No. Data lives in named Docker volumes (project folders under version control were rejected because designs live inside Postgres and versioning its binary files is unsafe). The volumes are documented together with the `down -v` warning; automated backups are out of scope.
- Q: Should the smoke test use a disposable stack separate from the real one? → A: Yes. It uses its own project name, its own volumes and different ports, removes the stack completely when it ends, and never touches the real stack.
- Q: Where should Claude Code store the MCP connection address that contains the key? → A: In user scope (personal configuration, outside the repository); the helper prints the command with the key masked.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a private Penpot instance locally (Priority: P1)

As the owner of the Mac, I want to start a complete Penpot instance with one command and open it in my browser, so that I have a design tool that runs entirely on my machine and is not reachable from other computers.

**Why this priority**: Everything else depends on a working, locked-down Penpot. It is also the smallest slice that already delivers value: a usable self-hosted design tool.

**Independent Test**: Start the stack from a clean checkout, wait until every service reports healthy, open the Penpot address in a browser, create an account, and create a design file. Confirm from another device on the same network that the instance is unreachable.

**Acceptance Scenarios**:

1. **Given** a Mac with only Docker installed and a freshly generated configuration, **When** I start the stack, **Then** every service reaches a healthy state without manual intervention.
2. **Given** the stack is healthy, **When** I open the Penpot address in my browser, **Then** I can register, log in, and create a design file.
3. **Given** the stack is running, **When** another device on my network tries to reach any published port, **Then** the connection is refused.
4. **Given** the stack is stopped and started again, **When** I log in, **Then** my account and design files are still there.

---

### User Story 2 - Let Claude Code read and modify designs (Priority: P1)

As a designer or developer, I want to connect Claude Code to my Penpot instance through MCP, so that the agent can inspect and change the design I have open.

**Why this priority**: This is the reason the project exists. It is P1 alongside Story 1 because Story 1 alone does not meet the goal.

**Independent Test**: With the stack running and a design file open, generate the MCP key, register the server in Claude Code, connect the open file, and ask Claude Code to describe the current page. A correct description proves the whole chain works.

**Acceptance Scenarios**:

1. **Given** a healthy stack and a Penpot account, **When** I enable MCP and generate a key in my account settings, **Then** I receive a connection address that already includes the key.
2. **Given** the connection address, **When** I register it in Claude Code, **Then** Claude Code lists the Penpot tools as available.
3. **Given** a design file open in a browser tab with the MCP plugin connected, **When** I ask Claude Code to read or change an element, **Then** the agent receives a valid answer and the change appears in the file.
4. **Given** the MCP plugin is not connected in any tab, **When** Claude Code calls a Penpot tool, **Then** the call fails, the documentation records the message the server returns and the step that fixes it, and connecting the plugin makes the same call succeed.

---

### User Story 3 - Verify the setup and keep it safe (Priority: P2)

As the maintainer, I want automated tests and a smoke test, so that I can trust the setup after any change and detect unsafe configuration before it reaches my machine.

**Why this priority**: It protects Stories 1 and 2 over time, but the system is usable without it, so it comes after them.

**Independent Test**: Run the unit tests and the smoke test using only Docker. Then introduce a deliberate mistake (an unpinned image tag, a port published on all interfaces, a missing health check) and confirm the tests fail.

**Acceptance Scenarios**:

1. **Given** a valid configuration, **When** I run the unit tests, **Then** they pass without installing anything on the host besides Docker.
2. **Given** a valid configuration, **When** I run the smoke test, **Then** it starts the stack, waits for healthy, and confirms the Penpot address and the MCP address both respond.
3. **Given** any Penpot image with a tag other than `2.18.4`, **When** the unit tests run, **Then** they fail and name the offending image.
4. **Given** a published port bound to any address other than the local machine, **When** the unit tests run, **Then** they fail and name the port.
5. **Given** a service without a health check, **When** the unit tests run, **Then** they fail and name the service.

---

### User Story 4 - Generate and protect secrets (Priority: P2)

As the maintainer, I want secrets generated for me and kept out of version control, so that I never commit a password or an MCP key by accident.

**Why this priority**: The instance works with default credentials, but that would break the project's security rules, so it follows right after the core flow.

**Independent Test**: Run the configuration generator on a clean checkout and inspect the result, the version control ignore rules, and every log line produced.

**Acceptance Scenarios**:

1. **Given** no configuration file exists, **When** I run the generator, **Then** it creates one with unique random secrets and a pinned Penpot version.
2. **Given** a configuration file already exists, **When** I run the generator, **Then** it leaves the file untouched and tells me so.
3. **Given** the generator or the connection helper produces output, **When** I read it, **Then** no secret or MCP key appears in clear text.
4. **Given** a clean checkout, **When** I list the files that version control would track, **Then** the real configuration file is absent and the example file contains placeholders only.

---

### Edge Cases

- A port needed by the stack is already used by another program on the Mac: startup must fail with a message that names the port, not hang.
- The installed Docker Compose does not apply the port restriction (an older version ignoring the override): the setup must detect that a port is published on a non-local address, name that port, and report the detected Compose version and that it must be upgraded. The exact minimum version is not claimed because it has not been verified.
- The MCP key is regenerated while Claude Code is still using the old one: the old connection stops working at once and the documentation must say so.
- The Penpot browser tab is closed, put to sleep, or unloaded by the browser during an agent session: the agent's call fails, the documentation explains the failure message and the fix, and reopening the tab restores the connection.
- A second browser tab tries to become the active MCP tab: only one tab can be active, and the documentation states which tab becomes active, as observed on this version.
- A service takes longer than usual to become healthy on first start (images still downloading, database initializing): the wait logic must tolerate this up to a documented limit and then fail with the name of the unhealthy service.
- The configuration file is deleted while the data volumes still exist, or its secrets are changed after the first run: the setup must refuse to generate new secrets while the real stack's database volume exists and must explain how to recover, so the user is not locked out of existing data.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST run Penpot release 2.18.4 and MUST use that exact version for every Penpot component; floating version tags MUST NOT be accepted.
- **FR-002**: The system MUST start the full Penpot stack, including the MCP service, with a single documented command on a Mac that has only Docker installed.
- **FR-003**: The system MUST NOT require any runtime other than Docker on the host machine.
- **FR-004**: The system MUST publish its ports only on the local machine; no port may be reachable from other devices by default.
- **FR-005**: The system MUST define a health check for every service and MUST expose an overall "all healthy" signal that the tests can wait on.
- **FR-006**: The system MUST persist the database and uploaded files across restarts, using named Docker volumes.
- **FR-007**: The system MUST keep secrets (application secret key, database credentials) out of version control and MUST provide an example configuration containing placeholders only.
- **FR-008**: The system MUST provide a generator that creates the real configuration with unique random secrets, MUST NOT overwrite an existing one, and MUST refuse to create a new one while the real stack's database volume already exists.
- **FR-009**: The system MUST serve MCP from the same Penpot address, with no additional published port and no additional container beyond those in the official stack.
- **FR-010**: The system MUST let a user generate an MCP key from the Penpot account settings and obtain a ready-to-use connection address.
- **FR-011**: The system MUST provide a helper that builds the Claude Code connection address and registration command, and MUST mask the MCP key in every output.
- **FR-012**: The system MUST document the operating rules for MCP: one key per user, regenerating it revokes the old one, one active MCP tab at a time, and the Penpot tab must stay open and awake during agent sessions.
- **FR-013**: The system MUST keep the official upstream configuration unmodified and apply all project-specific changes through a separate override file.
- **FR-014**: The system MUST include automated unit tests, written before the code they verify, covering the configuration generator, the merged-configuration validator, the connection helper with key masking, and the health-wait logic.
- **FR-015**: The unit tests MUST fail when an image uses a version other than 2.18.4, when any published port is not local-only, or when any service lacks a health check.
- **FR-016**: The system MUST include a smoke test that starts the stack, waits until it is healthy, and confirms that the Penpot address and the MCP address both respond.
- **FR-017**: All tests MUST run inside containers and MUST NOT require installing anything on the host besides Docker.
- **FR-018**: The system MUST fail with a clear, actionable message when a required port is busy, when Docker is unreachable, when the installed Docker Compose does not apply the port restriction, or when a service does not become healthy within the documented time limit.
- **FR-019**: The system MUST disable Penpot's anonymous telemetry, and the unit tests MUST fail if the merged configuration leaves it enabled.
- **FR-020**: The system MUST keep the mail catcher and the administration console from the official stack, each with a health check, and the mail catcher's web interface MUST be reachable only from the local machine.
- **FR-021**: All code, comments, test names, configuration comments, and commit messages MUST be written in English.
- **FR-022**: The documentation MUST name each volume, state what it holds (accounts and design files in the database volume, uploaded images and assets in the assets volume), and warn that removing volumes, for example with `docker compose down -v`, permanently deletes all accounts and designs.
- **FR-023**: The smoke test MUST run against a disposable stack with its own project name, its own volumes, its own local-only ports, and its own throwaway configuration (never the user's real configuration file), MUST remove that stack completely when it finishes (even on failure), and MUST NOT read, modify, or delete the user's real stack or its volumes.
- **FR-024**: The documented and helper-generated Claude Code registration MUST use the user scope, so the connection address and key are stored outside the repository, and the project MUST NOT create a project-scoped MCP configuration file containing the key.

### Key Entities

- **Penpot instance**: The running stack that hosts accounts and design files. Has a fixed version, a local-only address, and a set of services that must all be healthy.
- **Configuration file**: The private settings for one installation. Holds the pinned version and generated secrets. Never version-controlled. An example file with placeholders is the only tracked counterpart.
- **MCP key**: A personal, non-recoverable token tied to one Penpot user. Authenticates the AI client. Only one exists per user; regenerating it revokes the previous one.
- **Connection address**: The address Claude Code uses to reach the MCP service. Contains the MCP key, so it is treated as a secret.
- **MCP plugin session**: The live link between one open browser tab and the MCP service. Only one can be active at a time and it ends when the tab is closed or unloaded.
- **Override file**: The project-owned layer that adjusts the official configuration without editing it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a clean Mac with only Docker installed and the required images already downloaded, a user goes from checkout to a logged-in Penpot session in under 15 minutes. The first-time download (about 6.7 GB) is excluded because its duration depends on the user's connection; the documentation states its size.
- **SC-002**: After the first start, 100% of services report healthy within 3 minutes on a warm start.
- **SC-003**: A scan of all published ports finds 0 reachable from another device on the network.
- **SC-004**: A user completes the Claude Code connection, from opening account settings to the agent describing the open design, in under 10 minutes by following the documentation alone.
- **SC-005**: In 20 consecutive agent requests with the plugin connected, at least 19 succeed, and every failure carries a message that identifies its cause.
- **SC-006**: The full unit test suite finishes in under 60 seconds and the smoke test in under 5 minutes, both using only Docker.
- **SC-007**: Each of the deliberate mistakes (wrong version, port open to the network, missing health check) is caught by the tests in 100% of trials.
- **SC-008**: A search of the repository, the logs, and the generated output finds 0 occurrences of a real secret or MCP key in clear text.
- **SC-009**: Stopping and restarting the stack loses 0 accounts and 0 design files.

## Assumptions

- Automated backup and restore are out of scope for this version. Design files live inside the database, so project folders cannot version them safely; the user is warned instead (FR-022).
- The user owns the Mac, has administrator rights, and has Docker installed and running; no other tooling is installed or needed on the host.
- The instance is for one person or a small trusted group on one machine, not for exposure to the internet; HTTPS and public hosting are out of scope.
- Claude Code is the only AI client in scope. Other clients may work with the same address but are not tested.
- Email delivery is not required; with email verification disabled, accounts work without confirmation messages.
- The MCP service runs in the multi-user mode that the official image uses, which upstream marks as under development. The risk is accepted and documented.
- Penpot 2.18.4 is the only supported version. Upgrading is a separate, deliberate change governed by the project constitution.
- The official Docker images for 2.18.4 support both Intel and Apple Silicon Macs.
- A modern browser is available to host the Penpot tab and the MCP plugin; the user is responsible for keeping that tab awake during agent sessions.
- Open technical questions that do not change scope (which health-check tool each image offers, the exact minimum Docker Compose version for the override feature, and the exact Claude Code registration syntax) are resolved during planning with real tests against the 2.18.4 images, not in this specification.
- The decision records in `docs/2026-10-25-penpot-self-host-design.md` and the project constitution v1.1.0 apply to this feature.
