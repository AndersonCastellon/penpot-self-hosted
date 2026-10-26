"""The smoke orchestrator builds only commands that touch the disposable project (FR-016, FR-023)."""
import json
import random

import pytest

from model_builder import SERVICES, good_model
from penpot_selfhost import smoke

BUSY = (
    "Error response from daemon: failed to set up container networking: driver failed programming external "
    "connectivity on endpoint x: Bind for 127.0.0.1:34567 failed: port is already allocated"
)


def healthy_snapshot():
    return "\n".join(json.dumps({"Service": s, "State": "running", "Health": "healthy"}) for s in SERVICES)


class FakeRunner:
    """Scripted stand-in for the Docker CLI. Records every command it receives."""

    def __init__(self, up_results=None, leftovers=None, bindings=None, exec_code=0, network_code=0, model=None):
        self.model = model if model is not None else good_model()
        self.calls = []
        self.up_results = list(up_results or [(0, "", "")])
        self.leftovers = leftovers or {"containers": "", "volumes": "", "networks": ""}
        self.bindings = bindings or {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "34567"}], "5432/tcp": None}
        self.exec_code = exec_code
        self.network_code = network_code
        self.torn_down = False

    def __call__(self, argv):
        self.calls.append(list(argv))
        words = set(argv)
        if argv[:3] == ["docker", "network", "connect"] or argv[:3] == ["docker", "network", "disconnect"]:
            return self.network_code, "", ""
        if "up" in words:
            return self.up_results.pop(0) if len(self.up_results) > 1 else self.up_results[0]
        if "down" in words:
            self.torn_down = True
            return 0, "", ""
        if "config" in words:
            return 0, json.dumps(self.model), ""
        if "exec" in words:
            return self.exec_code, "", ""
        if argv[:2] == ["docker", "inspect"]:
            return 0, json.dumps(self.bindings), ""
        if argv[:3] == ["docker", "ps", "-a"]:
            return 0, self.leftovers["containers"] if self.torn_down else "abc123\n", ""
        if "json" in argv and "ps" in words:
            return 0, healthy_snapshot(), ""
        if "-q" in argv and "ps" in words:
            return 0, "abc123\ndef456\n", ""
        if argv[:3] == ["docker", "volume", "ls"]:
            return 0, self.leftovers["volumes"], ""
        if argv[:3] == ["docker", "network", "ls"]:
            return 0, self.leftovers["networks"], ""
        return 1, "", f"unexpected command: {argv}"


@pytest.fixture
def make(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / ".env").write_text("PENPOT_SECRET_KEY=REAL-USER-SECRET-MUST-NEVER-BE-READ\n")
    (root / "docker-compose.yaml").write_text("services: {}\n")
    (root / "docker-compose.override.yaml").write_text("services: {}\n")
    work = tmp_path / "work"
    work.mkdir()

    def build(runner, seed=1, **kwargs):
        return smoke.SmokeStack(
            runner, root=root, workdir=work, rng=random.Random(seed),
            clock=lambda: 0, sleeper=lambda seconds: None, self_id="selfcontainer", **kwargs,
        )

    build.root, build.work = root, work
    return build


# --- the project guard -------------------------------------------------------------------------


def test_the_project_name_is_fixed():
    assert smoke.PROJECT == "penpot-smoke"
    assert smoke.NETWORK == "penpot-smoke_penpot"


def test_a_stack_for_any_other_project_is_refused(make):
    with pytest.raises(smoke.SmokeError):
        make(FakeRunner(), project="penpot")


@pytest.mark.parametrize(
    "argv",
    [
        ["docker", "compose", "-p", "penpot", "down", "-v"],
        ["docker", "compose", "down", "-v"],
        ["docker", "volume", "rm", "penpot_penpot_postgres_v15"],
        ["docker", "rm", "-f", "somecontainer"],
        ["docker", "network", "connect", "penpot_default", "selfcontainer"],
        ["docker", "compose", "-f", "docker-compose.yaml", "up", "-d"],
        ["rm", "-rf", "/"],
    ],
)
def test_commands_that_could_touch_the_real_stack_are_refused(make, argv):
    runner = FakeRunner()
    stack = make(runner)

    with pytest.raises(smoke.SmokeError):
        stack.docker(argv)
    assert runner.calls == []


def test_every_command_of_a_full_run_names_only_the_disposable_project(make):
    runner = FakeRunner()
    stack = make(runner)

    stack.run(lambda s: (s.wait_healthy(), s.attach(), s.bindings(), s.exec_health_checks()))

    assert runner.calls
    for argv in runner.calls:
        text = " ".join(argv)
        assert "penpot-smoke" in text or argv[:2] == ["docker", "inspect"], argv
        assert " penpot " not in f" {text} ", argv


# --- the throwaway configuration ----------------------------------------------------------------


def test_the_env_file_is_generated_in_the_workdir_and_the_real_one_is_never_used(make):
    runner = FakeRunner()
    stack = make(runner)

    stack.run(lambda s: None)

    up = next(argv for argv in runner.calls if "up" in argv)
    env_path = up[up.index("--env-file") + 1]
    assert env_path == str(make.work / ".env")
    assert str(make.root / ".env") not in " ".join(" ".join(a) for a in runner.calls)
    values = dict(line.split("=", 1) for line in (make.work / ".env").read_text().splitlines())
    assert values["COMPOSE_PROJECT_NAME"] == "penpot-smoke"
    assert values["PENPOT_VERSION"] == "2.18.4"
    assert "REAL-USER-SECRET" not in (make.work / ".env").read_text()


def test_ports_are_random_high_distinct_and_exported_in_the_env_file(make):
    stack = make(FakeRunner())

    stack.run(lambda s: None)

    values = dict(line.split("=", 1) for line in (make.work / ".env").read_text().splitlines())
    http, mail = int(values["PENPOT_HTTP_PORT"]), int(values["PENPOT_MAIL_PORT"])
    assert 20000 <= http <= 59999 and 20000 <= mail <= 59999
    assert http != mail


def test_a_busy_port_retries_with_a_new_pair_and_cleans_up_in_between(make):
    runner = FakeRunner(up_results=[(1, "", BUSY), (0, "", "")])
    stack = make(runner)

    stack.run(lambda s: None)

    ups = [argv for argv in runner.calls if "up" in argv]
    downs = [argv for argv in runner.calls if "down" in argv]
    assert len(ups) == 2
    assert len(downs) >= 2  # one clean-up after the failed attempt, one final teardown


def test_three_busy_attempts_in_a_row_fail_with_a_clear_message(make):
    runner = FakeRunner(up_results=[(1, "", BUSY)])
    stack = make(runner)

    with pytest.raises(smoke.SmokeError) as error:
        stack.run(lambda s: None)

    assert "3" in str(error.value) and "port" in str(error.value).lower()
    assert len([argv for argv in runner.calls if "up" in argv]) == 3
    assert runner.torn_down


def test_an_unrelated_up_failure_is_not_retried(make):
    runner = FakeRunner(up_results=[(1, "", "pull access denied for penpotapp/mcp")])
    stack = make(runner)

    with pytest.raises(smoke.SmokeError) as error:
        stack.run(lambda s: None)

    assert "pull access denied" in str(error.value)
    assert len([argv for argv in runner.calls if "up" in argv]) == 1


# --- teardown -----------------------------------------------------------------------------------


def test_teardown_runs_even_when_a_step_fails(make):
    runner = FakeRunner()
    stack = make(runner)

    def boom(_):
        raise RuntimeError("probe exploded")

    with pytest.raises(RuntimeError):
        stack.run(boom)

    downs = [argv for argv in runner.calls if "down" in argv]
    assert downs and "-v" in downs[-1]
    assert any(argv[:3] == ["docker", "network", "disconnect"] for argv in runner.calls)


def test_leftovers_after_teardown_fail_the_run(make):
    runner = FakeRunner(leftovers={"containers": "", "volumes": "penpot-smoke_penpot_assets\n", "networks": ""})
    stack = make(runner)

    with pytest.raises(smoke.SmokeError) as error:
        stack.run(lambda s: None)

    assert "volumes" in str(error.value)
    assert "penpot-smoke_penpot_assets" in str(error.value)


def test_a_clean_teardown_reports_nothing_left(make):
    stack = make(FakeRunner())

    stack.run(lambda s: None)

    assert stack.leftovers() == []


# --- checks -------------------------------------------------------------------------------------


def test_bindings_are_read_from_docker_inspect(make):
    stack = make(FakeRunner())

    result = stack.run(lambda s: s.bindings())

    assert result == [("127.0.0.1", "34567")]


def test_a_binding_on_all_interfaces_is_reported(make):
    runner = FakeRunner(bindings={"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "34567"}]})
    stack = make(runner)

    assert stack.run(lambda s: s.bindings()) == [("0.0.0.0", "34567")]


def test_healthchecks_are_executed_through_compose_exec(make):
    runner = FakeRunner()
    stack = make(runner)

    failures = stack.run(lambda s: s.exec_health_checks())

    assert failures == []
    execs = [argv for argv in runner.calls if "exec" in argv]
    assert len(execs) == len(SERVICES)
    assert all("-T" in argv for argv in execs)


def test_dollar_signs_escaped_by_compose_config_are_unescaped_before_exec(make):
    # `docker compose config` prints "$" as "$$"; Compose unescapes it for real health checks, so the smoke
    # test must do the same or the shell would see the PID variable "$$" instead of the variable "line".
    model = good_model()
    model["services"]["penpot-frontend"]["healthcheck"]["test"] = ["CMD", "bash", "-c", '[[ "$$line" == *" 200 "* ]]']
    runner = FakeRunner(model=model)
    stack = make(runner)

    stack.run(lambda s: s.exec_health_checks())

    frontend = next(argv for argv in runner.calls if "exec" in argv and "penpot-frontend" in argv)
    assert frontend[-1] == '[[ "$line" == *" 200 "* ]]'


def test_a_failing_healthcheck_is_reported_naming_the_service(make):
    stack = make(FakeRunner(exec_code=1))

    failures = stack.run(lambda s: s.exec_health_checks())

    assert len(failures) == len(SERVICES)
    assert any("penpot-backend" in failure for failure in failures)


def test_attach_joins_the_disposable_network_only(make):
    runner = FakeRunner()
    stack = make(runner)

    stack.run(lambda s: s.attach())

    connects = [argv for argv in runner.calls if argv[:3] == ["docker", "network", "connect"]]
    assert connects == [["docker", "network", "connect", "penpot-smoke_penpot", "selfcontainer"]]
