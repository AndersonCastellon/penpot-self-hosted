"""Disposable-stack orchestration for the smoke test (FR-016, FR-023).

Everything here targets the Compose project "penpot-smoke" and nothing else. Every Docker command goes
through `SmokeStack.docker`, which refuses any command that could touch another project, the real stack or its
volumes. The stack uses a throwaway env file (never the user's .env) and random high ports, and it is
removed in a `finally` block, with a check that nothing is left behind.
"""
import json
import random
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from penpot_selfhost import envgen, healthwait, preflight

PROJECT = "penpot-smoke"
NETWORK = f"{PROJECT}_penpot"
LABEL = f"label=com.docker.compose.project={PROJECT}"
MAX_PORT_ATTEMPTS = 3
PORT_RANGE = (20000, 59999)
HEALTHY_LIMIT_SECONDS = 300

Runner = Callable[[List[str]], Tuple[int, str, str]]


class SmokeError(Exception):
    """The smoke run cannot continue or found something wrong."""


class SmokeStack:
    def __init__(
        self,
        runner: Runner,
        *,
        root: Path,
        workdir: Path,
        project: str = PROJECT,
        rng: Optional[random.Random] = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        self_id: Optional[str] = None,
    ):
        if project != PROJECT:
            raise SmokeError(f"The smoke test only manages the project {PROJECT}, not {project}.")
        self._runner = runner
        self._root = Path(root)
        self._workdir = Path(workdir)
        self._rng = rng or random.Random()
        self._clock = clock
        self._sleeper = sleeper
        self._self_id = self_id or socket.gethostname()
        self._container_ids: set = set()

    # --- the guard -------------------------------------------------------------------------------

    def _allowed(self, argv: List[str]) -> bool:
        if argv[:4] == ["docker", "compose", "-p", PROJECT]:
            return True
        if argv[:3] in (["docker", "network", "connect"], ["docker", "network", "disconnect"]):
            return argv[3:] == [NETWORK, self._self_id]
        if argv[:2] == ["docker", "inspect"]:
            return len(argv) > 2 and argv[-1] in self._container_ids
        for listing in (["docker", "ps", "-a"], ["docker", "volume", "ls"], ["docker", "network", "ls"]):
            if argv[: len(listing)] == listing:
                return argv[len(listing):] == ["--filter", LABEL, "-q"]
        return False

    def docker(self, argv: List[str]) -> Tuple[int, str, str]:
        """Run a Docker command, but only if it is one of the forms that touch the disposable project."""
        if not self._allowed(argv):
            raise SmokeError(f"Refused to run a command outside the {PROJECT} project: {' '.join(argv)}")
        return self._runner(argv)

    def compose(self, *args: str) -> List[str]:
        return [
            "docker", "compose", "-p", PROJECT,
            "--project-directory", str(self._root),
            "--env-file", str(self._workdir / ".env"),
            "-f", str(self._root / "docker-compose.yaml"),
            "-f", str(self._root / "docker-compose.override.yaml"),
            *args,
        ]

    # --- lifecycle -------------------------------------------------------------------------------

    def _pick_ports(self) -> Tuple[int, int]:
        http, mail = self._rng.sample(range(PORT_RANGE[0], PORT_RANGE[1] + 1), 2)
        return http, mail

    def start(self) -> None:
        """Generate a throwaway env, then `up -d`, retrying with new ports when a port is busy."""
        last = ""
        for _ in range(MAX_PORT_ATTEMPTS):
            http, mail = self._pick_ports()
            env_file = self._workdir / ".env"
            if env_file.exists():
                env_file.unlink()
            envgen.generate(self._workdir, [], project=PROJECT, http_port=http, mail_port=mail)

            code, _, err = self.docker(self.compose("up", "-d"))
            if code == 0:
                return
            last = preflight.explain_up_error(err)
            self.docker(self.compose("down", "-v"))
            if "is already in use" not in last:
                raise SmokeError(last)
        raise SmokeError(f"All {MAX_PORT_ATTEMPTS} attempts failed because the chosen ports were busy. Last: {last}")

    def wait_healthy(self, limit: int = HEALTHY_LIMIT_SECONDS) -> str:
        started = self._clock()
        while True:
            _, out, _ = self.docker(self.compose("ps", "--format", "json"))
            elapsed = int(self._clock() - started)
            verdict = healthwait.evaluate(healthwait.parse_ps(out), elapsed, limit)
            if verdict.kind == "healthy":
                return verdict.message
            if verdict.kind == "failed":
                raise SmokeError(verdict.message)
            self._sleeper(2)

    def attach(self) -> None:
        """Join the disposable network so the stack can be probed by service name."""
        code, _, err = self.docker(["docker", "network", "connect", NETWORK, self._self_id])
        if code != 0 and "already exists" not in err:
            raise SmokeError(f"Could not join the network {NETWORK}: {err.strip()}")

    # --- checks ----------------------------------------------------------------------------------

    def bindings(self) -> List[Tuple[str, str]]:
        """Return the (host address, host port) of every published port of the disposable stack."""
        _, out, _ = self.docker(self.compose("ps", "-q"))
        self._container_ids = set(out.split())
        found: List[Tuple[str, str]] = []
        for container in out.split():
            _, ports, _ = self.docker(["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container])
            for entries in (json.loads(ports) or {}).values():
                for entry in entries or []:
                    binding = (entry["HostIp"], entry["HostPort"])
                    if binding not in found:
                        found.append(binding)
        return found

    def exec_health_checks(self) -> List[str]:
        """Run each service's own health check command inside its container; return the failures."""
        _, out, _ = self.docker(self.compose("config", "--format", "json"))
        services: Dict = json.loads(out).get("services", {})
        failures = []
        for name, service in services.items():
            test = (service.get("healthcheck") or {}).get("test") or []
            if not test or test[0] == "NONE":
                failures.append(f"{name}: no health check")
                continue
            # `compose config` prints a literal "$" as "$$"; Compose unescapes it when it runs the real health check.
            test = [part.replace("$$", "$") for part in test]
            command = list(test[1:]) if test[0] == "CMD" else ["sh", "-c", test[1]]
            code, _, _ = self.docker(self.compose("exec", "-T", name, *command))
            if code != 0:
                failures.append(f"{name}: health check command exited with {code}")
        return failures

    # --- teardown --------------------------------------------------------------------------------

    def leftovers(self) -> List[str]:
        """Return what still exists for the disposable project (an empty list means it is clean)."""
        found = []
        for label, command in (
            ("containers", ["docker", "ps", "-a", "--filter", LABEL, "-q"]),
            ("volumes", ["docker", "volume", "ls", "--filter", LABEL, "-q"]),
            ("networks", ["docker", "network", "ls", "--filter", LABEL, "-q"]),
        ):
            _, out, _ = self.docker(command)
            if out.strip():
                found.append(f"{label}: {', '.join(out.split())}")
        return found

    def teardown(self) -> List[str]:
        """Disconnect, remove the stack with its volumes, and return anything left behind."""
        self.docker(["docker", "network", "disconnect", NETWORK, self._self_id])  # fails harmlessly if not attached
        self.docker(self.compose("down", "-v"))
        return self.leftovers()

    def run(self, callback: Callable[["SmokeStack"], object]):
        """Start the stack, call `callback`, and always tear it down; leftovers fail the run."""
        left: List[str] = []
        try:
            self.start()
            result = callback(self)
        finally:
            left = self.teardown()
        if left:
            raise SmokeError("Leftovers after teardown: " + "; ".join(left))
        return result


# --- HTTP probes used by the smoke tests ---------------------------------------------------------


def http_probe(url: str, *, method: str = "GET", body: Optional[bytes] = None, headers: Optional[dict] = None):
    """Return (status, headers) without raising on HTTP error codes."""
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers)
