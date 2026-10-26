"""Guard: no secret value reaches another file or any command output (FR-008, FR-011, SC-008)."""
import io
import json
from pathlib import Path

import pytest

from model_builder import good_model
from penpot_selfhost import cli

ROOT = Path(__file__).resolve().parents[2]
SECRET_KEYS = ("PENPOT_SECRET_KEY", "POSTGRES_PASSWORD")
SKIPPED_DIRS = {".git", "__pycache__", ".pytest_cache"}
TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".txt", ".json", ".example", ".sh", ""}


def secrets_from(env_path):
    values = {}
    for line in env_path.read_text().splitlines():
        key, _, value = line.partition("=")
        if key in SECRET_KEYS and value:
            values[key] = value
    return values


def repository_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name == ".env" or SKIPPED_DIRS & set(path.parts):
            continue
        if path.suffix in TEXT_SUFFIXES:
            yield path


@pytest.fixture
def generated(tmp_path):
    """A fresh .env produced by the real generator, plus the captured output of the commands that touch it."""
    captured = []

    def run(argv, env=None, runner=None):
        out, err = io.StringIO(), io.StringIO()
        cli.main(argv, stdout=out, stderr=err, stdin=io.StringIO(""), root=tmp_path, env=env or {}, runner=runner)
        captured.append(out.getvalue() + err.getvalue())

    run(["init", "--volumes", ""])
    run(["init", "--volumes", ""])  # second run: the "already exists" path
    run(["init", "--volumes", "penpot_penpot_postgres_v15"])  # the refusal path

    model_runner = lambda argv: (0, json.dumps(good_model()), "") if "config" in argv else (0, "5.1.2\n", "")
    run(["check"], runner=model_runner)

    broken = good_model()
    broken["services"]["penpot-backend"]["environment"]["PENPOT_SECRET_KEY"] = "change-this-insecure-key"
    run(["check"], runner=lambda argv: (0, json.dumps(broken), "") if "config" in argv else (0, "5.1.2\n", ""))

    secrets = secrets_from(tmp_path / ".env")
    run(["mcp-url"], env={"PENPOT_MCP_TOKEN": secrets["PENPOT_SECRET_KEY"]})  # worst case: a secret used as token
    return secrets, "\n".join(captured)


def test_generated_secrets_never_appear_in_command_output(generated):
    secrets, output = generated

    assert secrets, "the generator produced no secrets"
    for key, value in secrets.items():
        assert value not in output, f"{key} leaked into command output"


@pytest.mark.skipif(not (ROOT / ".env").exists(), reason="no real .env in this checkout")
def test_the_real_secrets_do_not_appear_in_any_other_file():
    secrets = secrets_from(ROOT / ".env")
    offenders = []
    for path in repository_files():
        text = path.read_text(errors="ignore")
        for key, value in secrets.items():
            if value in text:
                offenders.append(f"{key} in {path.relative_to(ROOT)}")

    assert offenders == []
