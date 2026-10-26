"""End-to-end smoke test on a DISPOSABLE stack (FR-016, FR-023). Run it with `bin/penpot smoke`.

It needs the Docker socket, so it only runs inside the `smoke` tools container. The stack uses the project
name "penpot-smoke", its own volumes, a throwaway env file and random local ports, and is removed at the end.
"""
import json
import socket
import tempfile
from pathlib import Path

import pytest

from penpot_selfhost import smoke
from penpot_selfhost.cli import default_runner

ROOT = Path("/work")

MCP_INITIALIZE = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "0"}},
    }
).encode()


@pytest.fixture(scope="module")
def stack():
    workdir = Path(tempfile.mkdtemp(prefix="penpot-smoke-"))
    disposable = smoke.SmokeStack(default_runner, root=ROOT, workdir=workdir, self_id=socket.gethostname())
    try:
        disposable.start()
        disposable.healthy_message = disposable.wait_healthy()
        disposable.attach()
        yield disposable
    finally:
        left = disposable.teardown()
    assert left == [], "Leftovers after teardown: " + "; ".join(left)


def test_every_service_becomes_healthy(stack):
    assert stack.healthy_message.startswith("healthy: 8/8")


def test_the_web_interface_answers(stack):
    status, _ = smoke.http_probe("http://penpot-frontend:8080/")

    assert status == 200


def test_the_mcp_endpoint_accepts_an_initialize_request(stack):
    status, headers = smoke.http_probe(
        "http://penpot-frontend:8080/mcp/stream",
        method="POST",
        body=MCP_INITIALIZE,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )

    assert status == 200
    assert {name.lower() for name in headers} >= {"mcp-session-id"}


def test_every_published_port_is_bound_to_loopback(stack):
    bindings = stack.bindings()

    assert len(bindings) >= 2
    assert [binding for binding in bindings if binding[0] != "127.0.0.1"] == []


def test_each_services_own_health_check_command_passes(stack):
    assert stack.exec_health_checks() == []
