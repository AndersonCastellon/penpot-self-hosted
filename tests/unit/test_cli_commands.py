"""Command wiring in penpot_selfhost.cli with injected paths, streams and runner (contracts/cli.md)."""
import io
import json
from pathlib import Path

from model_builder import SERVICES, good_model, mutated
from penpot_selfhost import cli

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class FakeRunner:
    """Stands in for subprocess: records calls and returns canned `docker compose` output."""

    def __init__(self, model=None, config_result=None, version="5.1.2"):
        self.model = good_model() if model is None else model
        self.config_result = config_result
        self.version = version
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        if "config" in argv:
            if self.config_result is not None:
                return self.config_result
            return 0, json.dumps(self.model), ""
        if "version" in argv:
            return 0, self.version + "\n", ""
        return 1, "", "unexpected call"


def run(argv, root, env=None, stdin="", runner=None):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(argv, stdout=out, stderr=err, stdin=io.StringIO(stdin), root=root, env=env or {}, runner=runner)
    return code, out.getvalue(), err.getvalue()


def snapshot(**overrides):
    entries = []
    for name in SERVICES:
        key = name.replace("-", "_")
        if overrides.get(key, "present") is None:
            continue
        state, health = overrides.get(key, ("running", "healthy"))
        entries.append({"Service": name, "State": state, "Health": health})
    return "\n".join(json.dumps(entry) for entry in entries)


# --- init -------------------------------------------------------------------------------------


def test_init_creates_env_and_reports_the_pinned_version(tmp_path):
    code, out, _ = run(["init", "--volumes", ""], tmp_path)

    assert code == cli.EXIT_OK
    assert out.strip() == "created .env (PENPOT_VERSION=2.18.4)"
    assert (tmp_path / ".env").exists()


def test_init_twice_changes_nothing_and_still_succeeds(tmp_path):
    run(["init", "--volumes", ""], tmp_path)
    before = (tmp_path / ".env").read_bytes()

    code, out, _ = run(["init", "--volumes", ""], tmp_path)

    assert code == cli.EXIT_OK
    assert out.strip() == ".env already exists, left untouched"
    assert (tmp_path / ".env").read_bytes() == before


def test_init_refuses_with_exit_1_when_the_data_volume_exists(tmp_path):
    code, out, err = run(["init", "--volumes", "alpha,penpot_penpot_postgres_v15"], tmp_path)

    assert code == cli.EXIT_FAILED
    assert out == ""
    assert "penpot_penpot_postgres_v15" in err
    assert "lock you out" in err
    assert not (tmp_path / ".env").exists()


def test_init_never_prints_the_generated_secrets(tmp_path):
    _, out, err = run(["init", "--volumes", ""], tmp_path)

    secrets = [line.partition("=")[2] for line in (tmp_path / ".env").read_text().splitlines()
               if line.startswith(("PENPOT_SECRET_KEY=", "POSTGRES_PASSWORD="))]
    assert secrets
    for secret in secrets:
        assert secret not in out + err


# --- check ------------------------------------------------------------------------------------


def prepared_root(tmp_path):
    (tmp_path / ".env").write_text("PENPOT_VERSION=2.18.4\n")
    return tmp_path


def test_check_succeeds_and_prints_the_summary(tmp_path):
    runner = FakeRunner()

    code, out, err = run(["check"], prepared_root(tmp_path), runner=runner)

    assert code == cli.EXIT_OK
    assert out.strip() == "OK: 8 services, 5 images pinned to 2.18.4, 2 ports local-only"
    config_call = next(call for call in runner.calls if "config" in call)
    assert config_call[:2] == ["docker", "compose"]
    assert "--env-file" in config_call and str(tmp_path / ".env") in config_call
    assert "--format" in config_call and "json" in config_call
    assert str(tmp_path / "docker-compose.override.yaml") in config_call


def test_check_without_env_is_a_prerequisite_error(tmp_path):
    code, out, err = run(["check"], tmp_path, runner=FakeRunner())

    assert code == cli.EXIT_USAGE
    assert "bin/penpot init" in err


def test_check_reports_violations_with_exit_1(tmp_path):
    broken = mutated(lambda m: m["services"]["penpot-backend"].update(image="penpotapp/backend:2.18"))

    code, out, err = run(["check"], prepared_root(tmp_path), runner=FakeRunner(model=broken))

    assert code == cli.EXIT_FAILED
    assert out == ""
    assert "Image penpotapp/backend:2.18 uses tag 2.18; expected 2.18.4." in err


def test_a_port_violation_adds_the_compose_version_hint(tmp_path):
    broken = mutated(lambda m: m["services"]["penpot-frontend"]["ports"][0].update(host_ip="0.0.0.0"))

    code, _, err = run(["check"], prepared_root(tmp_path), runner=FakeRunner(model=broken, version="2.20.1"))

    assert code == cli.EXIT_FAILED
    assert "Port 9001 of penpot-frontend is published on 0.0.0.0, expected 127.0.0.1." in err
    assert "Detected Compose 2.20.1" in err


def test_a_failing_compose_config_is_reported_with_exit_1(tmp_path):
    runner = FakeRunner(config_result=(1, "", "required variable PENPOT_VERSION is missing a value"))

    code, _, err = run(["check"], prepared_root(tmp_path), runner=runner)

    assert code == cli.EXIT_FAILED
    assert "PENPOT_VERSION" in err


# --- explain-up-error and check-ports ----------------------------------------------------------


def test_explain_up_error_prints_the_message_and_exits_1(tmp_path):
    text = (FIXTURES / "up_error_port_container.txt").read_text()

    code, out, err = run(["explain-up-error"], tmp_path, stdin=text)

    assert code == cli.EXIT_FAILED
    assert "Port 19990 is already in use by another container." in err


def test_check_ports_fails_when_a_program_holds_a_port(tmp_path):
    listing = "### PORT 9001\n" + (FIXTURES / "lsof_host_program.txt").read_text() + "### PORT 8025\n"

    code, out, err = run(["check-ports"], tmp_path, stdin=listing)

    assert code == cli.EXIT_FAILED
    assert "Port 9001 is already in use by Python (pid 15703)." in err


def test_check_ports_is_silent_when_everything_is_free(tmp_path):
    listing = "### PORT 9001\n### PORT 8025\n" + (FIXTURES / "lsof_docker_forwarder.txt").read_text()

    code, out, err = run(["check-ports"], tmp_path, stdin=listing)

    assert code == cli.EXIT_OK
    assert out == "" and err == ""


# --- mcp-url ------------------------------------------------------------------------------------

TOKEN = "abcdefgh12345678WXYZ"


def test_mcp_url_masks_the_token_by_default(tmp_path):
    code, out, err = run(["mcp-url"], tmp_path, env={"PENPOT_MCP_TOKEN": TOKEN})

    assert code == cli.EXIT_OK
    assert TOKEN not in out + err
    assert "claude mcp add --transport http --scope user penpot" in out
    assert "http://127.0.0.1:9001/mcp/stream?userToken=****" in out


def test_mcp_url_reveal_prints_the_full_command_on_stdout_only(tmp_path):
    code, out, err = run(["mcp-url", "--reveal"], tmp_path, env={"PENPOT_MCP_TOKEN": TOKEN})

    assert code == cli.EXIT_OK
    assert TOKEN in out
    assert TOKEN not in err


def test_mcp_url_uses_the_given_port(tmp_path):
    _, out, _ = run(["mcp-url", "--port", "9100"], tmp_path, env={"PENPOT_MCP_TOKEN": TOKEN})

    assert "http://127.0.0.1:9100/mcp/stream" in out


def test_mcp_url_rejects_a_token_passed_as_an_argument(tmp_path):
    code, out, err = run(["mcp-url", "--token", TOKEN], tmp_path, env={})

    assert code == cli.EXIT_USAGE
    assert TOKEN not in out + err


def test_mcp_url_without_a_token_is_a_prerequisite_error(tmp_path):
    code, out, err = run(["mcp-url"], tmp_path, env={})

    assert code == cli.EXIT_USAGE
    assert "PENPOT_MCP_TOKEN" in err
    assert out == ""


# --- health-verdict and format-status ----------------------------------------------------------


def verdict(tmp_path, stdin, *extra):
    return run(["health-verdict", "--elapsed", "41", "--limit", "180", *extra], tmp_path, stdin=stdin)


def test_health_verdict_healthy_exits_0_with_the_url(tmp_path):
    code, out, err = verdict(tmp_path, snapshot(), "--url", "http://127.0.0.1:9001")

    assert code == cli.EXIT_OK
    assert out.strip() == "healthy: 8/8 in 41s — http://127.0.0.1:9001"


def test_health_verdict_pending_exits_3(tmp_path):
    code, out, err = verdict(tmp_path, snapshot(penpot_backend=("running", "starting")))

    assert code == cli.EXIT_PENDING
    assert "penpot-backend" in out


def test_health_verdict_failed_exits_1_and_explains_on_stderr(tmp_path):
    code, out, err = verdict(tmp_path, snapshot(penpot_exporter=("exited", "")))

    assert code == cli.EXIT_FAILED
    assert "penpot-exporter" in err and "exited" in err


def test_health_verdict_requires_elapsed_and_limit(tmp_path):
    code, _, err = run(["health-verdict"], tmp_path, stdin=snapshot())

    assert code == cli.EXIT_USAGE
    assert "Usage" in err


def test_format_status_prints_a_table(tmp_path):
    code, out, _ = run(["format-status"], tmp_path, stdin=snapshot(penpot_mailpit=None))

    assert code == cli.EXIT_OK
    assert out.splitlines()[0].split() == ["SERVICE", "STATE", "HEALTH"]
    assert "penpot-mailpit" in out and "not" in out
