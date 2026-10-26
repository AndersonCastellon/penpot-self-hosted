"""bin/penpot is tested with fake `docker` and `lsof` executables first on PATH (constitution, Principle IV).

The shims record every call in $SHIM_LOG and behave according to SHIM_* environment variables,
so no real Docker daemon is involved.
"""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DISPATCHER = ROOT / "bin" / "penpot"

DOCKER_SHIM = r"""#!/usr/bin/env bash
echo "$*" >> "$SHIM_LOG"
case "$1" in
  info)
    [ "${SHIM_INFO_FAIL:-0}" = "1" ] && exit 1
    exit 0 ;;
  volume)
    for name in ${SHIM_VOLUMES:-}; do echo "$name"; done
    exit 0 ;;
esac
if [ "$1" = "compose" ]; then
  all="$*"
  case "$all" in
    *health-verdict*)
      cat > /dev/null
      if [ -s "$SHIM_VERDICTS" ]; then
        code=$(head -n 1 "$SHIM_VERDICTS")
        tail -n +2 "$SHIM_VERDICTS" > "$SHIM_VERDICTS.next"; mv "$SHIM_VERDICTS.next" "$SHIM_VERDICTS"
      else
        code=0
      fi
      echo "verdict-message-$code"
      exit "$code" ;;
    *check-ports*)
      cat > "$SHIM_LOG.stdin.check-ports"
      [ "${SHIM_CHECKPORTS_CODE:-0}" != "0" ] && echo "ports-busy-message" >&2
      exit "${SHIM_CHECKPORTS_CODE:-0}" ;;
    *explain-up-error*)
      cat > "$SHIM_LOG.stdin.explain-up-error"
      echo "explained-up-error" >&2
      exit 1 ;;
    *format-status*)
      cat > /dev/null
      echo "status-table"
      exit 0 ;;
    *" run "*) cat > /dev/null; exit 0 ;;
    *" up "*)
      if [ -n "${SHIM_UP_ERR:-}" ]; then echo "$SHIM_UP_ERR" >&2; exit 1; fi
      exit 0 ;;
    *" ps "*"-aq"*) printf '%s' "${SHIM_EXISTING:-}"; exit 0 ;;
    *" ps "*) echo "${SHIM_PS:-}"; exit 0 ;;
    *" down"*) exit 0 ;;
  esac
fi
exit 0
"""

LSOF_SHIM = r"""#!/usr/bin/env bash
echo "lsof $*" >> "$SHIM_LOG"
for arg in "$@"; do
  case "$arg" in
    -iTCP:*) port="${arg#-iTCP:}" ;;
  esac
done
if [ -f "$SHIM_LSOF_DIR/$port" ]; then cat "$SHIM_LSOF_DIR/$port"; fi
exit 0
"""


@pytest.fixture
def sandbox(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", DOCKER_SHIM), ("lsof", LSOF_SHIM)):
        shim = bin_dir / name
        shim.write_text(body)
        shim.chmod(0o755)
    log = tmp_path / "docker.log"
    log.write_text("")
    verdicts = tmp_path / "verdicts"
    verdicts.write_text("")
    lsof_dir = tmp_path / "lsof"
    lsof_dir.mkdir()
    env_file = tmp_path / "env"
    env_file.write_text("PENPOT_HTTP_PORT=9001\nPENPOT_MAIL_PORT=8025\n")
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "SHIM_LOG": str(log),
        "SHIM_VERDICTS": str(verdicts),
        "SHIM_LSOF_DIR": str(lsof_dir),
        "PENPOT_ENV_FILE": str(env_file),
        "PENPOT_POLL_SECONDS": "0",
        "HOME": str(tmp_path),
    }

    def run(*args, extra_env=None, verdict_codes=None, stdin=None):
        if verdict_codes is not None:
            verdicts.write_text("".join(f"{c}\n" for c in verdict_codes))
        merged = {**env, **(extra_env or {})}
        done = subprocess.run(["bash", str(DISPATCHER), *args], env=merged, capture_output=True, text=True, input=stdin)
        calls = [line for line in log.read_text().splitlines() if line]
        return done, calls

    run.log = log
    run.lsof_dir = lsof_dir
    run.env_file = env_file
    return run


def tool_calls(calls, subcommand):
    return [call for call in calls if " run " in call and subcommand in call]


# --- usage and Docker reachability -------------------------------------------------------------


def test_unknown_command_prints_usage_and_exits_2(sandbox):
    done, _ = sandbox("bogus")

    assert done.returncode == 2
    assert "Usage: bin/penpot" in done.stderr
    assert done.stdout == ""


def test_no_command_prints_usage_and_exits_2(sandbox):
    done, _ = sandbox()

    assert done.returncode == 2
    assert "Usage: bin/penpot" in done.stderr


@pytest.mark.parametrize("command", ["init", "up", "status", "down", "test"])
def test_unreachable_docker_gives_the_documented_message_and_starts_nothing(sandbox, command):
    done, calls = sandbox(command, extra_env={"SHIM_INFO_FAIL": "1"})

    assert done.returncode == 2
    assert "Docker is not reachable. Start your Docker runtime (Docker Desktop, OrbStack, ...) and retry." in done.stderr
    assert not any(call.startswith("compose") for call in calls)


# --- init collects volume names from the Mac's Docker -----------------------------------------


def test_init_forwards_the_existing_volume_names_to_the_tool(sandbox):
    done, calls = sandbox("init", extra_env={"SHIM_VOLUMES": "alpha beta"})

    assert done.returncode == 0
    assert any(call.startswith("volume ls") for call in calls)
    runs = tool_calls(calls, "init")
    assert len(runs) == 1
    assert "-T" in runs[0].split()
    assert "init --volumes alpha,beta" in runs[0]


def test_init_with_no_volumes_passes_an_empty_list(sandbox):
    done, calls = sandbox("init")

    runs = tool_calls(calls, "init")
    assert done.returncode == 0
    assert runs and runs[0].rstrip().endswith("init --volumes")


# --- check --------------------------------------------------------------------------------------


def test_check_runs_the_validator_in_the_tool_container(sandbox):
    done, calls = sandbox("check")

    runs = tool_calls(calls, "cli check")
    assert done.returncode == 0
    assert len(runs) == 1
    assert runs[0].rstrip().endswith("python3 -m penpot_selfhost.cli check")
    assert not any(" up " in call for call in calls)


# --- test / smoke --------------------------------------------------------------------------------


def test_test_runs_the_service_without_the_docker_socket(sandbox):
    done, calls = sandbox("test")

    runs = [call for call in calls if " run " in call]
    assert done.returncode == 0
    assert len(runs) == 1 and runs[0].rstrip().endswith("run --rm test")


def test_smoke_runs_the_only_service_that_has_the_docker_socket(sandbox):
    done, calls = sandbox("smoke")

    runs = [call for call in calls if " run " in call]
    assert done.returncode == 0
    assert len(runs) == 1 and runs[0].rstrip().endswith("run --rm smoke")
    assert not any(" up " in call or " down" in call for call in calls)


@pytest.mark.parametrize("command", ["init", "check", "up", "status", "down", "test", "mcp-url"])
def test_no_other_command_uses_the_socket_service(sandbox, command):
    _, calls = sandbox(command, extra_env={"PENPOT_MCP_TOKEN": "tokentokentoken"}, verdict_codes=[0])

    assert not any(call.rstrip().endswith(" smoke") or " run --rm smoke" in call for call in calls)


# --- mcp-url -------------------------------------------------------------------------------------

SECRET_TOKEN = "supersecrettoken1234567890"


def test_mcp_url_forwards_the_token_through_the_environment_only(sandbox):
    done, calls = sandbox("mcp-url", extra_env={"PENPOT_MCP_TOKEN": SECRET_TOKEN})

    runs = tool_calls(calls, "mcp-url")
    assert done.returncode == 0
    assert len(runs) == 1
    assert "-e PENPOT_MCP_TOKEN" in runs[0]
    assert SECRET_TOKEN not in "\n".join(calls)
    assert SECRET_TOKEN not in done.stdout + done.stderr


def test_mcp_url_prompts_for_a_missing_token_without_echoing_it(sandbox):
    stdin_token = "typedtoken_abcdefghijkl"

    done, calls = sandbox("mcp-url", stdin=stdin_token + "\n")

    assert done.returncode == 0
    assert stdin_token not in "\n".join(calls)
    assert stdin_token not in done.stdout + done.stderr
    assert "-e PENPOT_MCP_TOKEN" in tool_calls(calls, "mcp-url")[0]


def test_mcp_url_passes_the_port_from_the_env_file(sandbox):
    sandbox.env_file.write_text("PENPOT_HTTP_PORT=9100\nPENPOT_MAIL_PORT=9200\n")

    _, calls = sandbox("mcp-url", extra_env={"PENPOT_MCP_TOKEN": SECRET_TOKEN})

    assert "--port 9100" in tool_calls(calls, "mcp-url")[0]


def test_mcp_url_forwards_extra_flags(sandbox):
    _, calls = sandbox("mcp-url", "--reveal", extra_env={"PENPOT_MCP_TOKEN": SECRET_TOKEN})

    assert tool_calls(calls, "mcp-url")[0].rstrip().endswith("--reveal")


# --- down / status ------------------------------------------------------------------------------


def test_down_never_removes_volumes(sandbox):
    done, calls = sandbox("down")

    down_calls = [call for call in calls if call.startswith("compose") and call.rstrip().endswith("down")]
    assert done.returncode == 0
    assert len(down_calls) == 1
    assert " -v" not in down_calls[0] and "--volumes" not in down_calls[0]
    assert "stopped (volumes kept)" in done.stdout


def test_status_pipes_the_ps_snapshot_through_format_status(sandbox):
    done, calls = sandbox("status", extra_env={"SHIM_PS": '{"Service":"penpot-backend"}'})

    assert done.returncode == 0
    assert any(" ps " in call and "--format json" in call for call in calls)
    assert tool_calls(calls, "format-status")
    assert "status-table" in done.stdout


# --- up -----------------------------------------------------------------------------------------


def test_up_waits_until_the_verdict_is_healthy(sandbox):
    done, calls = sandbox("up", verdict_codes=[3, 3, 0])

    assert done.returncode == 0
    assert len(tool_calls(calls, "health-verdict")) == 3
    assert any(" up " in call and "-d" in call for call in calls)
    assert "verdict-message-0" in done.stdout


def test_up_passes_the_public_url_to_the_verdict(sandbox):
    done, calls = sandbox("up", verdict_codes=[0])

    assert "--url http://localhost:9001" in tool_calls(calls, "health-verdict")[0]


def test_up_fails_with_the_verdict_message_when_a_service_never_gets_healthy(sandbox):
    done, calls = sandbox("up", verdict_codes=[3, 1])

    assert done.returncode == 1
    assert "verdict-message-1" in done.stderr
    assert len(tool_calls(calls, "health-verdict")) == 2


def test_up_uses_the_longer_limit_on_a_first_start(sandbox):
    _, calls = sandbox("up", verdict_codes=[0], extra_env={"SHIM_EXISTING": ""})

    assert "--limit 300" in tool_calls(calls, "health-verdict")[0]


def test_up_uses_the_warm_limit_when_containers_already_exist(sandbox):
    _, calls = sandbox("up", verdict_codes=[0], extra_env={"SHIM_EXISTING": "abc123"})

    assert "--limit 180" in tool_calls(calls, "health-verdict")[0]


def test_up_explains_a_compose_up_failure_and_exits_1(sandbox):
    done, calls = sandbox("up", extra_env={"SHIM_UP_ERR": "Bind for 127.0.0.1:9001 failed: port is already allocated"})

    assert done.returncode == 1
    assert "explained-up-error" in done.stderr
    assert tool_calls(calls, "explain-up-error")
    stdin = Path(str(sandbox.log) + ".stdin.explain-up-error").read_text()
    assert "port is already allocated" in stdin
    assert not tool_calls(calls, "health-verdict")


def test_up_checks_the_mac_ports_before_starting_anything(sandbox):
    (sandbox.lsof_dir / "9001").write_text("COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\nPython 77 me 3u IPv4 0x1 0t0 TCP 127.0.0.1:9001 (LISTEN)\n")

    done, calls = sandbox("up", extra_env={"SHIM_CHECKPORTS_CODE": "1"})

    assert done.returncode == 1
    assert "ports-busy-message" in done.stderr
    assert not any(" up " in call and "-d" in call for call in calls)
    listing = Path(str(sandbox.log) + ".stdin.check-ports").read_text()
    assert "### PORT 9001" in listing and "Python 77" in listing and "### PORT 8025" in listing


def test_up_reads_the_ports_from_the_env_file(sandbox):
    sandbox.env_file.write_text("PENPOT_HTTP_PORT=9100\nPENPOT_MAIL_PORT=9200\n")

    _, calls = sandbox("up", verdict_codes=[0])

    lsof_ports = sorted(call.split("-iTCP:")[1].split()[0] for call in calls if call.startswith("lsof"))
    assert lsof_ports == ["9100", "9200"]
    assert "--url http://localhost:9100" in tool_calls(calls, "health-verdict")[0]


def test_up_uses_default_ports_when_the_env_file_is_missing(sandbox):
    sandbox.env_file.unlink()

    _, calls = sandbox("up", verdict_codes=[0])

    lsof_ports = sorted(call.split("-iTCP:")[1].split()[0] for call in calls if call.startswith("lsof"))
    assert lsof_ports == ["8025", "9001"]
