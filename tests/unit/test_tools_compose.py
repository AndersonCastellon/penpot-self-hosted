"""Only the smoke service may have the Docker socket (plan.md, Complexity Tracking; research R8)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_COMPOSE = ROOT / "tools" / "compose.tools.yaml"


def service_blocks():
    """Split the services section of compose.tools.yaml into {name: text} (simple, indentation based)."""
    lines = TOOLS_COMPOSE.read_text().splitlines()
    start = lines.index("services:") + 1
    blocks, current = {}, None
    for line in lines[start:]:
        if line.startswith("  ") and not line.startswith("   ") and line.strip().endswith(":"):
            current = line.strip()[:-1]
            blocks[current] = []
        elif current is not None:
            blocks[current].append(line)
    return {name: "\n".join(body) for name, body in blocks.items()}


def test_the_three_tool_services_exist():
    assert set(service_blocks()) == {"test", "tool", "smoke"}


def test_only_the_smoke_service_mounts_the_docker_socket():
    blocks = service_blocks()

    assert "docker.sock" in blocks["smoke"]
    assert "docker.sock" not in blocks["test"]
    assert "docker.sock" not in blocks["tool"]


def test_the_socket_is_not_mentioned_outside_the_smoke_service():
    text = TOOLS_COMPOSE.read_text()
    header = text.split("services:")[0]

    assert "docker.sock" not in header


def test_the_test_service_cannot_write_to_the_project():
    assert ":ro" in service_blocks()["test"]


def test_the_smoke_service_mounts_the_project_read_only():
    assert "..:/work:ro" in service_blocks()["smoke"]


def test_the_smoke_service_runs_the_smoke_tests():
    assert "tests/smoke" in service_blocks()["smoke"]
