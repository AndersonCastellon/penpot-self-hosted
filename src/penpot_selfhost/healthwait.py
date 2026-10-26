"""Pure health-wait logic (FR-005, FR-018; data-model: state machine of the stack).

There is no clock and no sleep here: the dispatcher bin/penpot polls `docker compose ps` and calls
`evaluate` with the elapsed time (research R11).
"""
import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from penpot_selfhost.composecheck import SERVICES

# States that will not recover on their own. Every other non-healthy state keeps waiting until the limit.
_DEAD_STATES = ("exited", "dead", "removing")


@dataclass(frozen=True)
class Verdict:
    kind: str  # "healthy", "pending" or "failed"
    message: str
    service: Optional[str] = None


def parse_ps(text: str) -> List[Dict]:
    """Parse `docker compose ps --format json`, which is JSON lines or a JSON array depending on version."""
    text = text.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if parsed is None:
            return []
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def _problem(entry: Optional[Dict]) -> Optional[str]:
    """Describe why a service is not healthy yet, or return None when it is healthy."""
    if entry is None:
        return "not running"
    state = (entry.get("State") or "").lower()
    health = (entry.get("Health") or "").lower()
    if state in _DEAD_STATES:
        return f"exited ({state})"
    if state == "running" and health == "":
        return "no health check"
    if state == "running" and health == "healthy":
        return None
    return f"{state}/{health or 'starting'}"


def evaluate(snapshot: List[Dict], elapsed: int, limit: int) -> Verdict:
    """Decide whether the stack is healthy, still starting, or failed (naming the first culprit)."""
    by_service = {entry.get("Service"): entry for entry in snapshot}
    pending = []

    for name in SERVICES:
        entry = by_service.get(name)
        problem = _problem(entry)
        if problem is None:
            continue
        state = (entry.get("State") or "").lower() if entry else ""
        if problem == "no health check":
            return Verdict("failed", f"Service {name} has no health check.", name)
        if state in _DEAD_STATES:
            return Verdict("failed", f"Service {name} exited. Run: docker compose logs {name}", name)
        pending.append((name, problem))

    if not pending:
        return Verdict("healthy", f"healthy: {len(SERVICES)}/{len(SERVICES)} in {elapsed}s")

    name, problem = pending[0]
    if elapsed >= limit:
        return Verdict(
            "failed",
            f"Service {name} is {problem} after {elapsed}s (limit {limit}s). Run: docker compose logs {name}",
            name,
        )
    waiting = ", ".join(service for service, _ in pending)
    return Verdict("pending", f"pending: waiting for {waiting} ({elapsed}s of {limit}s)", name)


def format_status(snapshot: List[Dict]) -> str:
    """Render a table with one line per expected service."""
    by_service = {entry.get("Service"): entry for entry in snapshot}
    rows = [("SERVICE", "STATE", "HEALTH")]
    for name in SERVICES:
        entry = by_service.get(name)
        if entry is None:
            rows.append((name, "not created", "-"))
        else:
            rows.append((name, entry.get("State") or "-", entry.get("Health") or "-"))
    widths = [max(len(row[column]) for row in rows) for column in range(3)]
    return "\n".join("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in rows)
