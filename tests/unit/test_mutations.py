"""Every deliberate mistake is caught, applied to the REAL merged configuration (SC-007, FR-015).

test_composecheck.py proves each check on a synthetic model. This file proves the same mistakes are caught
when they are applied to the model rendered from the real docker-compose files.
"""
import copy
import json
import subprocess
from pathlib import Path

import pytest

from penpot_selfhost import composecheck
from test_composecheck import MUTATIONS

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def real_model():
    command = [
        "docker", "compose",
        "--project-directory", str(ROOT),
        "--env-file", str(ROOT / ".env.example"),
        "-f", str(ROOT / "docker-compose.yaml"),
        "-f", str(ROOT / "docker-compose.override.yaml"),
        "config", "--format", "json",
    ]
    done = subprocess.run(command, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_unmodified_real_model_is_valid(real_model):
    assert composecheck.check(real_model) == []


@pytest.mark.parametrize("mutation, culprit", [(m, c) for _, m, c in MUTATIONS], ids=[i for i, _, _ in MUTATIONS])
def test_every_mistake_is_caught_on_the_real_model(real_model, mutation, culprit):
    model = copy.deepcopy(real_model)
    mutation(model)

    violations = composecheck.check(model)

    assert violations, "the mistake was not detected"
    assert any(culprit in violation for violation in violations), violations


def test_the_set_of_mistakes_covers_every_category_of_check():
    ids = {mutation_id for mutation_id, _, _ in MUTATIONS}

    for required in ("floating-2.18", "open-port", "no-healthcheck", "telemetry-on", "upstream-secret-key",
                     "missing-database-volume", "missing-admin-console", "extra-service"):
        assert required in ids
