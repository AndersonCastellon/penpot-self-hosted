"""Builds merged Compose models (the JSON of `docker compose config --format json`) for tests."""
import copy

VERSION = "2.18.4"

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

PUBLIC_URI = "http://localhost:9001"

FLAGS = (
    "disable-email-verification enable-smtp enable-prepl-server "
    "disable-secure-session-cookies enable-mcp enable-admin-console"
)

ASSETS_MOUNT = {"type": "volume", "source": "penpot_assets", "target": "/opt/data/assets"}
DATABASE_MOUNT = {"type": "volume", "source": "penpot_postgres_v15", "target": "/var/lib/postgresql/data"}


def _service(image, health=("CMD", "true"), ports=None, environment=None, volumes=None):
    service = {"image": image, "healthcheck": {"test": list(health), "interval": "10s"}}
    if ports:
        service["ports"] = ports
    if environment:
        service["environment"] = dict(environment)
    if volumes:
        service["volumes"] = list(volumes)
    return service


def _local_port(published, target):
    return {"mode": "ingress", "host_ip": "127.0.0.1", "target": target, "published": str(published), "protocol": "tcp"}


def good_model():
    """A merged model that satisfies every check."""
    secret = "s" * 64
    password = "p" * 32
    model = {
        "name": "penpot",
        "services": {
            "penpot-frontend": _service(
                f"penpotapp/frontend:{VERSION}",
                ports=[_local_port(9001, 8080)],
                environment={"PENPOT_FLAGS": FLAGS, "PENPOT_PUBLIC_URI": PUBLIC_URI},
                volumes=[ASSETS_MOUNT],
            ),
            "penpot-backend": _service(
                f"penpotapp/backend:{VERSION}",
                environment={
                    "PENPOT_FLAGS": FLAGS,
                    "PENPOT_PUBLIC_URI": PUBLIC_URI,
                    "PENPOT_TELEMETRY_ENABLED": "false",
                    "PENPOT_SECRET_KEY": secret,
                    "PENPOT_DATABASE_PASSWORD": password,
                },
                volumes=[ASSETS_MOUNT],
            ),
            "penpot-mcp": _service(f"penpotapp/mcp:{VERSION}", health=("CMD", "node", "-e", "process.exit(0)")),
            "penpot-exporter": _service(
                f"penpotapp/exporter:{VERSION}",
                environment={"PENPOT_FLAGS": FLAGS, "PENPOT_PUBLIC_URI": PUBLIC_URI, "PENPOT_SECRET_KEY": secret},
            ),
            "penpot-admin-console": _service(
                f"penpotapp/admin-console:{VERSION}",
                health=("CMD", "node", "-e", "process.exit(0)"),
                environment={"PENPOT_PUBLIC_URI": PUBLIC_URI, "PENPOT_SECRET_KEY": secret, "PENPOT_DATABASE_PASSWORD": password},
            ),
            "penpot-postgres": _service(
                "postgres:15",
                environment={"POSTGRES_PASSWORD": password, "POSTGRES_USER": "penpot"},
                volumes=[DATABASE_MOUNT],
            ),
            "penpot-valkey": _service("valkey/valkey:8.1"),
            "penpot-mailpit": _service("axllent/mailpit:v1", ports=[_local_port(8025, 8025)]),
        },
        "volumes": {"penpot_postgres_v15": {"name": "penpot_penpot_postgres_v15"}, "penpot_assets": {"name": "penpot_penpot_assets"}},
    }
    return model


def mutated(mutate):
    """Return a deep copy of the good model after applying `mutate(model)`."""
    model = copy.deepcopy(good_model())
    mutate(model)
    return model
