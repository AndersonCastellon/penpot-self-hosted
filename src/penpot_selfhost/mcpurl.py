"""Build the MCP connection address and the Claude Code registration command (FR-011, FR-012, FR-024).

The address contains the user's MCP key, so every string produced here is masked unless the caller
explicitly asks to reveal it. The key is never stored by the project.
"""
from urllib.parse import quote

from penpot_selfhost.masking import mask_url

HOST = "127.0.0.1"
PATH = "/mcp/stream"
DEFAULT_PORT = 9001

OPERATING_RULES = (
    "There is one key per user. Regenerating it revokes the previous one immediately, "
    "and any client still using the old key stops working.",
    "There is one active MCP tab at a time: only one browser tab can be connected.",
    "The Penpot tab with the MCP plugin connected must stay open and awake during agent sessions; "
    "if the browser puts it to sleep or unloads it, the connection is lost until you reopen it.",
    "The MCP endpoint accepts any token: access to it is limited by the 127.0.0.1 binding. "
    "The token only pairs the agent with the browser tab whose plugin uses the same key.",
)


def build_url(port: int, token: str) -> str:
    """Return the connection address that Penpot shows next to the generated key."""
    return f"http://{HOST}:{port}{PATH}?userToken={quote(token, safe='')}"


def registration_command(url: str) -> str:
    """Return the Claude Code command; user scope keeps the key outside the repository (FR-024)."""
    return f'claude mcp add --transport http --scope user penpot "{url}"'


def render(port: int, token: str, reveal: bool = False) -> str:
    """Return the full help text. The token is masked unless `reveal` is true."""
    url = build_url(port, token)
    command = registration_command(url if reveal else mask_url(url))
    lines = [
        "Register Penpot in Claude Code (user scope, so the key stays outside this repository):",
        "",
        f"  {command}",
        "",
    ]
    if not reveal:
        lines += ["The key is masked. Run `bin/penpot mcp-url --reveal` to print the full command.", ""]
    lines += [
        "Then, in Penpot, open a design file and choose File > MCP Server > Connect.",
        "",
        "Operating rules:",
    ]
    lines += [f"  - {rule}" for rule in OPERATING_RULES]
    return "\n".join(lines)
