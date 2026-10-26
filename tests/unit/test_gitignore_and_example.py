"""Guard: .env is ignored by git and .env.example holds placeholders only (FR-007, SC-008)."""
from pathlib import Path

from penpot_selfhost import envgen

ROOT = Path(__file__).resolve().parents[2]

SECRET_KEYS = ("PENPOT_SECRET_KEY", "POSTGRES_PASSWORD")
PLACEHOLDER = "change-me"


def parse(path):
    values = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key] = value
    return values


def test_env_is_ignored_by_git():
    patterns = [line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()]

    assert ".env" in patterns


def test_the_example_lists_exactly_the_keys_the_generator_writes():
    assert list(parse(ROOT / ".env.example")) == list(envgen.ENV_KEYS)


def test_every_secret_in_the_example_is_the_placeholder():
    values = parse(ROOT / ".env.example")

    for key in SECRET_KEYS:
        assert values[key] == PLACEHOLDER, f"{key} in .env.example must be '{PLACEHOLDER}'"


def test_the_example_contains_no_long_random_looking_value():
    for key, value in parse(ROOT / ".env.example").items():
        assert len(value) < 32, f"{key} looks like a real secret"


def test_the_example_pins_the_penpot_version():
    assert parse(ROOT / ".env.example")["PENPOT_VERSION"] == envgen.PENPOT_VERSION == "2.18.4"
