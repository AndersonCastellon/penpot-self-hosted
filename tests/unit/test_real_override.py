"""The real docker-compose.yaml + docker-compose.override.yaml, rendered by `docker compose config`.

`config` is client-side, so this runs in the test container without the Docker socket (research R5).
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

from penpot_selfhost import composecheck

ROOT = Path(__file__).resolve().parents[2]


def render(extra_env=None):
    command = [
        "docker", "compose",
        "--project-directory", str(ROOT),
        "--env-file", str(ROOT / ".env.example"),
        "-f", str(ROOT / "docker-compose.yaml"),
        "-f", str(ROOT / "docker-compose.override.yaml"),
        "config", "--format", "json",
    ]
    environment = {"PATH": os.environ["PATH"], **(extra_env or {})}
    done = subprocess.run(command, capture_output=True, text=True, env=environment)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def merged():
    return render()


def test_the_real_configuration_passes_every_check(merged):
    assert composecheck.check(merged) == []


def test_postgres_uses_the_configured_password_not_the_upstream_literal(merged):
    # Upstream declares POSTGRES_* in list form; the override uses map form (research outstanding item 2).
    environment = merged["services"]["penpot-postgres"]["environment"]

    assert environment["POSTGRES_PASSWORD"] == "change-me"
    assert environment["POSTGRES_PASSWORD"] != "penpot"


def test_all_database_passwords_come_from_the_same_setting(merged):
    services = merged["services"]

    assert services["penpot-backend"]["environment"]["PENPOT_DATABASE_PASSWORD"] == "change-me"
    assert services["penpot-admin-console"]["environment"]["PENPOT_DATABASE_PASSWORD"] == "change-me"


def test_published_ports_use_the_configured_variables(merged):
    frontend = merged["services"]["penpot-frontend"]["ports"][0]
    mailpit = merged["services"]["penpot-mailpit"]["ports"][0]

    assert (frontend["host_ip"], frontend["published"], frontend["target"]) == ("127.0.0.1", "9001", 8080)
    assert (mailpit["host_ip"], mailpit["published"], mailpit["target"]) == ("127.0.0.1", "8025", 8025)


def test_the_upstream_version_fallback_cannot_apply(merged):
    tags = {name: service["image"].rsplit(":", 1)[1] for name, service in merged["services"].items() if service["image"].startswith("penpotapp/")}

    assert set(tags.values()) == {"2.18.4"}
    assert len(tags) == 5


PUBLIC_URI_SERVICES = ("penpot-frontend", "penpot-backend", "penpot-exporter", "penpot-admin-console")


def test_the_public_uri_matches_the_default_port(merged):
    for name in PUBLIC_URI_SERVICES:
        assert merged["services"][name]["environment"]["PENPOT_PUBLIC_URI"] == "http://localhost:9001", name


def test_changing_the_http_port_moves_the_public_uri_with_it():
    # The UI calls the API at PENPOT_PUBLIC_URI; if it kept port 9001 the browser would block every request (CORS).
    custom = render({"PENPOT_HTTP_PORT": "9100"})

    for name in PUBLIC_URI_SERVICES:
        assert custom["services"][name]["environment"]["PENPOT_PUBLIC_URI"] == "http://localhost:9100", name
    assert custom["services"]["penpot-frontend"]["ports"][0]["published"] == "9100"
    assert composecheck.check(custom) == []
