"""Guard: the MCP key must never end up in a project-scoped config file (FR-024, spec clarification Q5)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_there_is_no_project_scoped_mcp_config_file():
    assert not (ROOT / ".mcp.json").exists(), ".mcp.json would hold the MCP key inside the repository"


def test_mcp_json_is_ignored_by_git():
    lines = [line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()]

    assert ".mcp.json" in lines


def test_no_module_writes_a_project_scoped_mcp_file():
    offenders = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "src").rglob("*.py")
        if ".mcp.json" in path.read_text() or "--scope project" in path.read_text()
    ]

    assert offenders == []


def test_the_registration_always_uses_user_scope():
    sources = "\n".join(path.read_text() for path in (ROOT / "src").rglob("*.py"))

    assert "--scope user" in sources
