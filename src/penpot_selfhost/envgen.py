"""Generate the private .env file (FR-007, FR-008, data-model: ConfigFile).

The generator never calls Docker: the names of existing volumes are an argument, collected by
bin/penpot (research R11). It never overwrites an existing file and never returns secret values.
"""
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PENPOT_VERSION = "2.18.4"
DEFAULT_PROJECT = "penpot"
DEFAULT_HTTP_PORT = 9001
DEFAULT_MAIL_PORT = 8025

# Order matters: it is the order of the lines written to .env and of .env.example.
ENV_KEYS = (
    "PENPOT_VERSION",
    "COMPOSE_PROJECT_NAME",
    "PENPOT_HTTP_PORT",
    "PENPOT_MAIL_PORT",
    "PENPOT_SECRET_KEY",
    "POSTGRES_PASSWORD",
)

DATABASE_VOLUME_SUFFIX = "penpot_postgres_v15"

_MIN_PORT, _MAX_PORT = 1024, 65535


class EnvError(ValueError):
    """Invalid settings. The message names the offending key and never shows a secret value."""


@dataclass(frozen=True)
class Result:
    status: str  # "created", "exists" or "refused"
    message: str


def database_volume_name(project: str) -> str:
    return f"{project}_{DATABASE_VOLUME_SUFFIX}"


def _validate(version: str, http_port: int, mail_port: int) -> None:
    if version != PENPOT_VERSION:
        raise EnvError(f"PENPOT_VERSION must be exactly {PENPOT_VERSION}")
    for key, port in (("PENPOT_HTTP_PORT", http_port), ("PENPOT_MAIL_PORT", mail_port)):
        if not _MIN_PORT <= port <= _MAX_PORT:
            raise EnvError(f"{key} must be between {_MIN_PORT} and {_MAX_PORT}")
    if http_port == mail_port:
        raise EnvError("PENPOT_MAIL_PORT must differ from PENPOT_HTTP_PORT")


def _refusal(volume: str) -> str:
    return (
        f"Database volume {volume} already exists but .env is missing. New secrets would lock you "
        "out of your data. Restore your previous .env, or remove the volumes on purpose "
        "(this deletes all accounts and designs)."
    )


def generate(
    root: Path,
    existing_volumes: Iterable[str],
    *,
    project: str = DEFAULT_PROJECT,
    version: str = PENPOT_VERSION,
    http_port: int = DEFAULT_HTTP_PORT,
    mail_port: int = DEFAULT_MAIL_PORT,
    env_name: str = ".env",
) -> Result:
    """Create `root/.env` unless it exists or the real stack's database volume is present."""
    _validate(version, http_port, mail_port)
    target = Path(root) / env_name

    if target.exists():
        return Result("exists", f"{env_name} already exists, left untouched")

    volume = database_volume_name(project)
    if volume in set(existing_volumes):
        return Result("refused", _refusal(volume))

    values = {
        "PENPOT_VERSION": version,
        "COMPOSE_PROJECT_NAME": project,
        "PENPOT_HTTP_PORT": str(http_port),
        "PENPOT_MAIL_PORT": str(mail_port),
        # token_urlsafe(48) is 64 URL-safe characters, token_urlsafe(24) is 32.
        "PENPOT_SECRET_KEY": secrets.token_urlsafe(48),
        "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
    }
    content = "".join(f"{key}={values[key]}\n" for key in ENV_KEYS)

    # O_EXCL makes "never overwrite" race-free; 0600 keeps the secrets private to the user.
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return Result("exists", f"{env_name} already exists, left untouched")
    with os.fdopen(descriptor, "w") as handle:
        handle.write(content)

    return Result("created", f"created {env_name} (PENPOT_VERSION={version})")
