"""Validate the merged Compose model (`docker compose config --format json`).

Pure functions: no Docker, no I/O. Every violation is one human-readable line that names the
culprit (image, port, service, variable or volume) and never contains a secret value.
Checks are listed in specs/001-penpot-selfhost-mcp/data-model.md, "MergedComposeModel".
"""
from typing import Dict, List

EXPECTED_VERSION = "2.18.4"
LOCAL_ADDRESS = "127.0.0.1"

# The eight services of the official stack (FR-009, FR-020), in stack order.
SERVICES = (
    "penpot-frontend",
    "penpot-backend",
    "penpot-mcp",
    "penpot-exporter",
    "penpot-admin-console",
    "penpot-postgres",
    "penpot-valkey",
    "penpot-mailpit",
)

# Services built from the five official Penpot images, which must all share the pinned tag.
PENPOT_IMAGES = {
    "penpot-frontend": "penpotapp/frontend",
    "penpot-backend": "penpotapp/backend",
    "penpot-exporter": "penpotapp/exporter",
    "penpot-admin-console": "penpotapp/admin-console",
    "penpot-mcp": "penpotapp/mcp",
}

# The only services allowed to publish a port.
PUBLISHING_SERVICES = ("penpot-frontend", "penpot-mailpit")

# These images are hardened and have no shell, so their health checks must use the exec form.
NO_SHELL_SERVICES = ("penpot-mcp", "penpot-admin-console")

DATABASE_VOLUME = "penpot_postgres_v15"
ASSETS_VOLUME = "penpot_assets"
DATABASE_SERVICE = "penpot-postgres"
ASSETS_SERVICES = ("penpot-backend", "penpot-frontend")

# Services that receive PENPOT_PUBLIC_URI. The browser UI calls the API at this address, so it must be exactly
# the origin the user opens: if it names another host or port, every request is blocked by CORS.
PUBLIC_URI_SERVICES = ("penpot-frontend", "penpot-backend", "penpot-exporter", "penpot-admin-console")
PUBLIC_HOST = "localhost"

# Literal values shipped in the upstream docker-compose.yaml; they must never survive the override.
UPSTREAM_LITERALS = (
    ("PENPOT_SECRET_KEY", "change-this-insecure-key"),
    ("PENPOT_DATABASE_PASSWORD", "penpot"),
    ("POSTGRES_PASSWORD", "penpot"),
)


def _image_tag(image: str) -> str:
    """Return the tag of an image reference, or an empty string when it has none."""
    name = image.rsplit("/", 1)[-1]
    return name.split(":", 1)[1] if ":" in name else ""


def _check_services_present(services: Dict) -> List[str]:
    violations = []
    for name in SERVICES:
        if name not in services:
            violations.append(f"Service {name} is missing; the official stack must keep all {len(SERVICES)} services.")
    for name in services:
        if name not in SERVICES:
            violations.append(f"Service {name} is not part of the official stack.")
    return violations


def _check_images(services: Dict) -> List[str]:
    violations = []
    for name, expected_name in PENPOT_IMAGES.items():
        if name not in services:
            continue
        image = services[name].get("image", "")
        tag = _image_tag(image)
        repository = image.rsplit(":", 1)[0] if tag else image
        if repository != expected_name or tag != EXPECTED_VERSION:
            shown = tag if tag else "(none)"
            violations.append(f"Image {image} uses tag {shown}; expected {EXPECTED_VERSION}.")
    return violations


def _check_ports(services: Dict) -> List[str]:
    violations = []
    for name, service in services.items():
        ports = service.get("ports") or []
        if ports and name not in PUBLISHING_SERVICES:
            violations.append(f"Service {name} publishes a port; only {', '.join(PUBLISHING_SERVICES)} may.")
        for port in ports:
            if not port.get("published"):
                continue
            address = port.get("host_ip") or "0.0.0.0"
            if address != LOCAL_ADDRESS:
                violations.append(
                    f"Port {port['published']} of {name} is published on {address}, expected {LOCAL_ADDRESS}."
                )
    return violations


def _check_health(services: Dict) -> List[str]:
    violations = []
    for name, service in services.items():
        test = (service.get("healthcheck") or {}).get("test") or []
        if not test or test[0] == "NONE":
            violations.append(f"Service {name} has no health check.")
        elif name in NO_SHELL_SERVICES and test[0] != "CMD":
            violations.append(f"Service {name} has no shell: its health check must use the exec form (CMD), not {test[0]}.")
    return violations


def _check_telemetry(services: Dict) -> List[str]:
    backend = services.get("penpot-backend")
    if backend is None:
        return []
    environment = backend.get("environment") or {}
    violations = []
    if environment.get("PENPOT_TELEMETRY_ENABLED") != "false":
        violations.append("Variable PENPOT_TELEMETRY_ENABLED of penpot-backend must be \"false\".")
    for name, service in services.items():
        if "enable-telemetry" in ((service.get("environment") or {}).get("PENPOT_FLAGS") or "").split():
            violations.append(f"Flag enable-telemetry is set in PENPOT_FLAGS of {name}.")
    return violations


def _check_secrets(services: Dict) -> List[str]:
    violations = []
    for name, service in services.items():
        environment = service.get("environment") or {}
        for variable, literal in UPSTREAM_LITERALS:
            if environment.get(variable) == literal:
                violations.append(f"Variable {variable} of {name} still has the upstream default value.")
    return violations


def _published_http_port(services: Dict) -> str:
    for port in (services.get("penpot-frontend") or {}).get("ports") or []:
        if port.get("published"):
            return str(port["published"])
    return ""


def _check_public_uri(services: Dict) -> List[str]:
    port = _published_http_port(services)
    if not port:
        return []
    expected = f"http://{PUBLIC_HOST}:{port}"
    violations = []
    for name in PUBLIC_URI_SERVICES:
        if name not in services:
            continue
        value = (services[name].get("environment") or {}).get("PENPOT_PUBLIC_URI")
        if value != expected:
            violations.append(
                f"Variable PENPOT_PUBLIC_URI of {name} is {value or '(unset)'}; expected {expected} "
                "(the browser origin must match the published port, or the UI cannot reach the API)."
            )
    return violations


def _mounts(service: Dict) -> set:
    return {mount.get("source") for mount in (service.get("volumes") or []) if mount.get("type") == "volume"}


def _check_volumes(model: Dict, services: Dict) -> List[str]:
    violations = []
    volumes = model.get("volumes") or {}
    for volume in (DATABASE_VOLUME, ASSETS_VOLUME):
        if volume not in volumes:
            violations.append(f"Named volume {volume} is not declared.")
    if DATABASE_SERVICE in services and DATABASE_VOLUME not in _mounts(services[DATABASE_SERVICE]):
        violations.append(f"Service {DATABASE_SERVICE} does not mount the named volume {DATABASE_VOLUME}.")
    for name in ASSETS_SERVICES:
        if name in services and ASSETS_VOLUME not in _mounts(services[name]):
            violations.append(f"Service {name} does not mount the named volume {ASSETS_VOLUME}.")
    return violations


def check(model: Dict) -> List[str]:
    """Return every violation found in a merged Compose model (an empty list means it is valid)."""
    services = model.get("services") or {}
    return (
        _check_services_present(services)
        + _check_images(services)
        + _check_ports(services)
        + _check_health(services)
        + _check_telemetry(services)
        + _check_secrets(services)
        + _check_public_uri(services)
        + _check_volumes(model, services)
    )


def summary(model: Dict) -> str:
    """One-line success message for a valid model."""
    services = model.get("services") or {}
    published = sum(1 for service in services.values() for port in service.get("ports") or [] if port.get("published"))
    images = sum(1 for name in PENPOT_IMAGES if name in services)
    return f"OK: {len(services)} services, {images} images pinned to {EXPECTED_VERSION}, {published} ports local-only"
