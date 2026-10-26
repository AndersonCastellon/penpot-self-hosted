"""The .env generator (FR-007, FR-008, data-model: ConfigFile)."""
import os
import stat

import pytest

from penpot_selfhost import envgen


def read_env(path):
    values = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key] = value
    return values


def test_creates_env_with_pinned_version_and_project_name(tmp_path):
    result = envgen.generate(tmp_path, existing_volumes=[])

    assert result.status == "created"
    values = read_env(tmp_path / ".env")
    assert values["PENPOT_VERSION"] == "2.18.4"
    assert values["COMPOSE_PROJECT_NAME"] == "penpot"
    assert values["PENPOT_HTTP_PORT"] == "9001"
    assert values["PENPOT_MAIL_PORT"] == "8025"


def test_writes_exactly_the_documented_keys(tmp_path):
    envgen.generate(tmp_path, existing_volumes=[])

    assert list(read_env(tmp_path / ".env")) == list(envgen.ENV_KEYS)


def test_secrets_are_long_url_safe_and_random(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()

    envgen.generate(first, existing_volumes=[])
    envgen.generate(second, existing_volumes=[])

    a, b = read_env(first / ".env"), read_env(second / ".env")
    assert len(a["PENPOT_SECRET_KEY"]) >= 64
    assert len(a["POSTGRES_PASSWORD"]) >= 32
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert set(a["PENPOT_SECRET_KEY"] + a["POSTGRES_PASSWORD"]) <= allowed
    assert a["PENPOT_SECRET_KEY"] != b["PENPOT_SECRET_KEY"]
    assert a["POSTGRES_PASSWORD"] != b["POSTGRES_PASSWORD"]
    assert a["PENPOT_SECRET_KEY"] != a["POSTGRES_PASSWORD"]


def test_env_file_is_private(tmp_path):
    envgen.generate(tmp_path, existing_volumes=[])

    mode = stat.S_IMODE(os.stat(tmp_path / ".env").st_mode)
    assert mode == 0o600


def test_existing_env_is_left_byte_identical(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes(b"PENPOT_SECRET_KEY=keep-me\n")

    result = envgen.generate(tmp_path, existing_volumes=["penpot_penpot_postgres_v15"])

    assert result.status == "exists"
    assert result.message == ".env already exists, left untouched"
    assert env.read_bytes() == b"PENPOT_SECRET_KEY=keep-me\n"


def test_refuses_when_the_data_volume_exists_but_env_is_missing(tmp_path):
    result = envgen.generate(tmp_path, existing_volumes=["penpot_penpot_postgres_v15"])

    assert result.status == "refused"
    assert not (tmp_path / ".env").exists()
    assert "penpot_penpot_postgres_v15" in result.message
    assert "lock you out" in result.message


def test_unrelated_volumes_do_not_block_creation(tmp_path):
    result = envgen.generate(tmp_path, existing_volumes=["other_project_data", "penpot-smoke_penpot_postgres_v15"])

    assert result.status == "created"


def test_the_refusal_uses_the_given_project_name(tmp_path):
    result = envgen.generate(tmp_path, existing_volumes=["demo_penpot_postgres_v15"], project="demo")

    assert result.status == "refused"


@pytest.mark.parametrize(
    "kwargs, key",
    [
        ({"version": "2.18"}, "PENPOT_VERSION"),
        ({"version": "latest"}, "PENPOT_VERSION"),
        ({"http_port": 80}, "PENPOT_HTTP_PORT"),
        ({"http_port": 70000}, "PENPOT_HTTP_PORT"),
        ({"mail_port": 1}, "PENPOT_MAIL_PORT"),
        ({"http_port": 9100, "mail_port": 9100}, "PENPOT_MAIL_PORT"),
    ],
)
def test_invalid_settings_are_rejected_naming_the_key(tmp_path, kwargs, key):
    with pytest.raises(envgen.EnvError) as error:
        envgen.generate(tmp_path, existing_volumes=[], **kwargs)

    assert key in str(error.value)
    assert not (tmp_path / ".env").exists()


def test_messages_never_contain_the_generated_secrets(tmp_path):
    result = envgen.generate(tmp_path, existing_volumes=[])

    values = read_env(tmp_path / ".env")
    assert values["PENPOT_SECRET_KEY"] not in result.message
    assert values["POSTGRES_PASSWORD"] not in result.message
