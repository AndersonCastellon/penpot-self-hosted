"""Preflight decisions made from facts the host collected (research R11).

Containers cannot see the Mac's ports, so bin/penpot runs `lsof` and `docker compose up` on the Mac
and hands the raw text to these pure functions.
"""
import re
from typing import Dict, List, Optional, Tuple

from penpot_selfhost.masking import mask_url

_ADVICE = "Set PENPOT_HTTP_PORT or PENPOT_MAIL_PORT in .env, or free the port."

# Daemon wording when another container holds the port, and the generic socket wording.
_BUSY_PATTERNS = (
    re.compile(r"Bind for [^\s:]*:(\d+) failed: port is already allocated"),
    re.compile(r"(?:listen tcp|bind)[^\n]*?:(\d+)[^\n]*address already in use", re.IGNORECASE),
    re.compile(r"port (\d+) is already allocated", re.IGNORECASE),
)

# Processes that belong to the Docker runtime: they forward the stack's own ports and are not conflicts.
_RUNTIME_PREFIXES = ("com.docke", "docker", "orbstack", "vpnkit", "limactl", "lima", "colima", "rancher", "podman")

_PORT_MARKER = re.compile(r"^### PORT (\d+)\s*$")


def explain_up_error(stderr: str) -> str:
    """Turn the stderr of a failed `docker compose up -d` into one actionable message."""
    for pattern in _BUSY_PATTERNS:
        match = pattern.search(stderr)
        if match:
            return f"Port {match.group(1)} is already in use by another container. {_ADVICE}"
    lines = [line for line in stderr.strip().splitlines() if line.strip()]
    detail = mask_url(lines[-1].strip()) if lines else "no details were reported"
    return f"docker compose up failed: {detail}"


def port_holders(lsof_output: str) -> List[Tuple[str, int]]:
    """Return (command, pid) of programs listening on a port, ignoring the Docker runtime itself."""
    holders = []
    for line in lsof_output.splitlines():
        columns = line.split()
        if len(columns) < 2 or columns[0] == "COMMAND" or not columns[1].isdigit():
            continue
        command = columns[0]
        if command.lower().startswith(_RUNTIME_PREFIXES):
            continue
        holders.append((command, int(columns[1])))
    return holders


def parse_port_listings(text: str) -> Dict[int, str]:
    """Split the dispatcher's text (`### PORT <n>` followed by lsof output) into one entry per port."""
    listings: Dict[int, str] = {}
    current: Optional[int] = None
    for line in text.splitlines(keepends=True):
        marker = _PORT_MARKER.match(line.rstrip("\n"))
        if marker:
            current = int(marker.group(1))
            listings[current] = ""
        elif current is not None:
            listings[current] += line
    return listings


def explain_busy_ports(listings: Dict[int, str]) -> Optional[str]:
    """Return a message for the first port held by a program on the Mac, or None when all are free."""
    for port, output in listings.items():
        holders = port_holders(output)
        if holders:
            command, pid = holders[0]
            return f"Port {port} is already in use by {command} (pid {pid}). {_ADVICE}"
    return None


def compose_version_hint(version: str) -> str:
    """Hint appended to port-binding violations. The minimum version is deliberately not claimed."""
    return f"Detected Compose {version}; this version may not apply the port override, upgrade Docker Compose."
