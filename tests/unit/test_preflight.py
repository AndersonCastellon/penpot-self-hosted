"""Preflight decisions: busy ports and `compose up` errors (spec edge cases 1 and 2, FR-018)."""
from pathlib import Path

import pytest

from penpot_selfhost import preflight

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def fixture(name):
    return (FIXTURES / name).read_text()


# --- explain_up_error (the daemon reports a port held by another container) --------------------


def test_a_port_held_by_another_container_is_explained():
    message = preflight.explain_up_error(fixture("up_error_port_container.txt"))

    assert message == (
        "Port 19990 is already in use by another container. "
        "Set PENPOT_HTTP_PORT or PENPOT_MAIL_PORT in .env, or free the port."
    )


def test_address_already_in_use_is_also_recognised():
    text = "Error: listen tcp 0.0.0.0:9001: bind: address already in use"

    assert "Port 9001 is already in use" in preflight.explain_up_error(text)


def test_an_unrelated_error_keeps_the_original_text():
    message = preflight.explain_up_error("pull access denied for penpotapp/mcp")

    assert message.startswith("docker compose up failed:")
    assert "pull access denied for penpotapp/mcp" in message


def test_an_unrelated_error_is_masked_if_it_contains_a_token():
    message = preflight.explain_up_error("failed http://h/mcp/stream?userToken=abcdefgh12345678")

    assert "abcdefgh12345678" not in message


def test_an_empty_error_still_produces_a_message():
    assert preflight.explain_up_error("").startswith("docker compose up failed")


# --- busy ports held by a program on the Mac (research R11) -----------------------------------


def test_a_program_listening_on_the_port_is_a_holder():
    holders = preflight.port_holders(fixture("lsof_host_program.txt"))

    assert holders == [("Python", 15703)]


def test_the_docker_runtime_forwarder_is_not_a_holder():
    # OrbStack, Docker Desktop (com.docker.backend) and friends forward the stack's own ports.
    assert preflight.port_holders(fixture("lsof_docker_forwarder.txt")) == []


@pytest.mark.parametrize("command", ["com.docke", "docker", "OrbStack", "vpnkit", "limactl", "colima"])
def test_known_runtime_processes_are_ignored(command):
    text = f"COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n{command} 42 me 3u IPv4 0x1 0t0 TCP 127.0.0.1:9001 (LISTEN)\n"

    assert preflight.port_holders(text) == []


@pytest.mark.parametrize("text", ["", "\n", "COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n"])
def test_empty_or_header_only_lsof_output_means_free(text):
    assert preflight.port_holders(text) == []


def test_parse_port_listings_splits_the_dispatcher_format():
    text = "### PORT 9001\n" + fixture("lsof_host_program.txt") + "### PORT 8025\n"

    listings = preflight.parse_port_listings(text)

    assert set(listings) == {9001, 8025}
    assert "Python" in listings[9001]
    assert listings[8025].strip() == ""


def test_busy_ports_message_names_port_and_program():
    listings = {9001: fixture("lsof_host_program.txt"), 8025: ""}

    message = preflight.explain_busy_ports(listings)

    assert message == (
        "Port 9001 is already in use by Python (pid 15703). "
        "Set PENPOT_HTTP_PORT or PENPOT_MAIL_PORT in .env, or free the port."
    )


def test_no_busy_ports_gives_no_message():
    assert preflight.explain_busy_ports({9001: fixture("lsof_docker_forwarder.txt"), 8025: ""}) is None


# --- Compose version hint ---------------------------------------------------------------------


def test_the_version_hint_names_the_detected_version():
    hint = preflight.compose_version_hint("2.20.1")

    assert "2.20.1" in hint
    assert "upgrade Docker Compose" in hint
    assert "minimum" not in hint  # the minimum version is unverified, so it is never claimed
