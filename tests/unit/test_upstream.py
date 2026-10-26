"""Guard: docker-compose.yaml must stay byte-identical to the official Penpot 2.18.4 file."""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yaml"
UPSTREAM_NOTE = ROOT / "UPSTREAM.md"


def recorded_sha256() -> str:
    match = re.search(r"^- sha256: ([0-9a-f]{64})$", UPSTREAM_NOTE.read_text(), re.MULTILINE)
    assert match, "UPSTREAM.md must contain a line like '- sha256: <64 hex characters>'"
    return match.group(1)


def test_compose_file_matches_recorded_hash():
    actual = hashlib.sha256(COMPOSE.read_bytes()).hexdigest()
    assert actual == recorded_sha256(), (
        "docker-compose.yaml was modified. Put project changes in docker-compose.override.yaml."
    )


def test_compose_file_is_the_upstream_with_its_floating_version_fallback():
    # The override must neutralise this fallback; seeing it here proves the file is untouched.
    assert "${PENPOT_VERSION:-2.18}" in COMPOSE.read_text()
