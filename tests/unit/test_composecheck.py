"""The merged-Compose validator (FR-001, FR-004, FR-005, FR-006, FR-009, FR-015, FR-019, FR-020)."""
import pytest

from model_builder import good_model, mutated
from penpot_selfhost import composecheck


def test_a_good_model_has_no_violations():
    assert composecheck.check(good_model()) == []


def test_summary_counts_services_images_and_local_ports():
    assert composecheck.summary(good_model()) == "OK: 8 services, 5 images pinned to 2.18.4, 2 ports local-only"


def set_image(service, image):
    def apply(model):
        model["services"][service]["image"] = image
    return apply


def drop_health(service):
    def apply(model):
        del model["services"][service]["healthcheck"]
    return apply


def set_port(service, **changes):
    def apply(model):
        model["services"][service]["ports"][0].update(changes)
    return apply


def drop_host_ip(service):
    def apply(model):
        del model["services"][service]["ports"][0]["host_ip"]
    return apply


def publish_extra(service, published):
    def apply(model):
        model["services"][service]["ports"] = [
            {"mode": "ingress", "host_ip": "127.0.0.1", "target": 4401, "published": str(published), "protocol": "tcp"}
        ]
    return apply


def set_env(service, key, value):
    def apply(model):
        model["services"][service].setdefault("environment", {})[key] = value
    return apply


def remove_service(name):
    def apply(model):
        del model["services"][name]
    return apply


def add_service(name):
    def apply(model):
        model["services"][name] = {"image": "busybox:1", "healthcheck": {"test": ["CMD", "true"]}}
    return apply


def drop_volume(name):
    def apply(model):
        del model["volumes"][name]
    return apply


def unmount(service):
    def apply(model):
        model["services"][service]["volumes"] = []
    return apply


def cmd_shell(service):
    def apply(model):
        model["services"][service]["healthcheck"]["test"] = ["CMD-SHELL", "true"]
    return apply


MUTATIONS = [
    # (id, mutation, text that MUST appear in a violation)
    ("floating-2.18", set_image("penpot-backend", "penpotapp/backend:2.18"), "penpotapp/backend:2.18"),
    ("latest", set_image("penpot-frontend", "penpotapp/frontend:latest"), "penpotapp/frontend:latest"),
    ("no-tag", set_image("penpot-mcp", "penpotapp/mcp"), "penpotapp/mcp"),
    ("other-version", set_image("penpot-exporter", "penpotapp/exporter:2.17.0"), "penpotapp/exporter:2.17.0"),
    ("wrong-image-name", set_image("penpot-admin-console", "someone/else:2.18.4"), "someone/else:2.18.4"),
    ("open-port", set_port("penpot-frontend", host_ip="0.0.0.0"), "9001"),
    ("no-host-ip", drop_host_ip("penpot-mailpit"), "8025"),
    ("extra-published-port", publish_extra("penpot-mcp", 4401), "penpot-mcp"),
    ("no-healthcheck", drop_health("penpot-valkey"), "penpot-valkey"),
    ("healthcheck-none", lambda m: m["services"]["penpot-backend"].update(healthcheck={"test": ["NONE"]}), "penpot-backend"),
    ("shell-healthcheck-mcp", cmd_shell("penpot-mcp"), "penpot-mcp"),
    ("shell-healthcheck-admin", cmd_shell("penpot-admin-console"), "penpot-admin-console"),
    ("telemetry-on", set_env("penpot-backend", "PENPOT_TELEMETRY_ENABLED", "true"), "PENPOT_TELEMETRY_ENABLED"),
    ("telemetry-unset", lambda m: m["services"]["penpot-backend"]["environment"].pop("PENPOT_TELEMETRY_ENABLED"), "PENPOT_TELEMETRY_ENABLED"),
    ("telemetry-flag", set_env("penpot-backend", "PENPOT_FLAGS", "enable-mcp enable-telemetry"), "enable-telemetry"),
    ("upstream-secret-key", set_env("penpot-backend", "PENPOT_SECRET_KEY", "change-this-insecure-key"), "PENPOT_SECRET_KEY"),
    ("upstream-db-password", set_env("penpot-admin-console", "PENPOT_DATABASE_PASSWORD", "penpot"), "PENPOT_DATABASE_PASSWORD"),
    ("upstream-postgres-password", set_env("penpot-postgres", "POSTGRES_PASSWORD", "penpot"), "POSTGRES_PASSWORD"),
    ("public-uri-wrong-port", set_env("penpot-frontend", "PENPOT_PUBLIC_URI", "http://localhost:9999"), "PENPOT_PUBLIC_URI"),
    ("public-uri-127", set_env("penpot-backend", "PENPOT_PUBLIC_URI", "http://127.0.0.1:9001"), "PENPOT_PUBLIC_URI"),
    ("public-uri-missing", lambda m: m["services"]["penpot-exporter"]["environment"].pop("PENPOT_PUBLIC_URI"), "PENPOT_PUBLIC_URI"),
    ("missing-database-volume", drop_volume("penpot_postgres_v15"), "penpot_postgres_v15"),
    ("missing-assets-volume", drop_volume("penpot_assets"), "penpot_assets"),
    ("database-not-mounted", unmount("penpot-postgres"), "penpot_postgres_v15"),
    ("assets-not-mounted", unmount("penpot-backend"), "penpot_assets"),
    ("missing-admin-console", remove_service("penpot-admin-console"), "penpot-admin-console"),
    ("missing-mailpit", remove_service("penpot-mailpit"), "penpot-mailpit"),
    ("extra-service", add_service("penpot-extra"), "penpot-extra"),
]


@pytest.mark.parametrize("mutation, culprit", [(m, c) for _, m, c in MUTATIONS], ids=[i for i, _, _ in MUTATIONS])
def test_every_deliberate_mistake_is_caught_and_names_the_culprit(mutation, culprit):
    violations = composecheck.check(mutated(mutation))

    assert violations, "the mistake was not detected"
    assert any(culprit in violation for violation in violations), violations


@pytest.mark.parametrize("secret_key", ["change-this-insecure-key"])
def test_violations_never_print_secret_values(secret_key):
    model = mutated(set_env("penpot-backend", "PENPOT_SECRET_KEY", secret_key))
    model["services"]["penpot-postgres"]["environment"]["POSTGRES_PASSWORD"] = "penpot"

    text = "\n".join(composecheck.check(model))

    assert secret_key not in text
    assert "POSTGRES_PASSWORD" in text


def test_port_violation_text_follows_the_cli_contract():
    violations = composecheck.check(mutated(set_port("penpot-frontend", host_ip="0.0.0.0")))

    assert "Port 9001 of penpot-frontend is published on 0.0.0.0, expected 127.0.0.1." in violations


def test_image_violation_text_follows_the_cli_contract():
    violations = composecheck.check(mutated(set_image("penpot-backend", "penpotapp/backend:2.18")))

    assert "Image penpotapp/backend:2.18 uses tag 2.18; expected 2.18.4." in violations


def test_the_public_uri_follows_the_published_port():
    model = good_model()
    model["services"]["penpot-frontend"]["ports"][0]["published"] = "9100"
    for name in ("penpot-frontend", "penpot-backend", "penpot-exporter", "penpot-admin-console"):
        model["services"][name]["environment"]["PENPOT_PUBLIC_URI"] = "http://localhost:9100"

    assert composecheck.check(model) == []


def test_the_public_uri_violation_explains_the_browser_origin_rule():
    violations = composecheck.check(mutated(set_env("penpot-frontend", "PENPOT_PUBLIC_URI", "http://localhost:9999")))

    assert any("expected http://localhost:9001" in v and "browser" in v for v in violations)
