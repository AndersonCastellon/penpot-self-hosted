"""Pure health-wait logic: evaluate(snapshot, elapsed, limit) (FR-005, FR-018, data-model state machine)."""
import json

import pytest

from model_builder import SERVICES
from penpot_selfhost import healthwait

LIMIT = 180


def snapshot(**overrides):
    """A `compose ps` snapshot with every service running and healthy, minus/plus overrides.

    overrides: service name with dashes replaced by underscores -> (state, health) or None to drop it.
    """
    entries = []
    for name in SERVICES:
        key = name.replace("-", "_")
        if overrides.get(key, "present") is None:
            continue
        state, health = overrides.get(key, ("running", "healthy"))
        entries.append({"Service": name, "State": state, "Health": health})
    return entries


def test_all_healthy_is_healthy():
    verdict = healthwait.evaluate(snapshot(), elapsed=41, limit=LIMIT)

    assert verdict.kind == "healthy"
    assert verdict.message == "healthy: 8/8 in 41s"


def test_a_starting_service_before_the_limit_is_pending():
    verdict = healthwait.evaluate(snapshot(penpot_backend=("running", "starting")), elapsed=30, limit=LIMIT)

    assert verdict.kind == "pending"
    assert "penpot-backend" in verdict.message


def test_a_starting_service_at_the_limit_fails_naming_it():
    verdict = healthwait.evaluate(snapshot(penpot_backend=("running", "starting")), elapsed=LIMIT, limit=LIMIT)

    assert verdict.kind == "failed"
    assert verdict.service == "penpot-backend"
    assert verdict.message == (
        "Service penpot-backend is running/starting after 180s (limit 180s). Run: docker compose logs penpot-backend"
    )


def test_an_unhealthy_service_is_pending_until_the_limit_then_fails():
    broken = snapshot(penpot_mcp=("running", "unhealthy"))

    assert healthwait.evaluate(broken, elapsed=60, limit=LIMIT).kind == "pending"
    failed = healthwait.evaluate(broken, elapsed=LIMIT + 5, limit=LIMIT)
    assert failed.kind == "failed" and failed.service == "penpot-mcp"


def test_an_exited_service_fails_immediately():
    verdict = healthwait.evaluate(snapshot(penpot_exporter=("exited", "")), elapsed=2, limit=LIMIT)

    assert verdict.kind == "failed"
    assert verdict.service == "penpot-exporter"
    assert "exited" in verdict.message


def test_a_running_service_without_a_health_check_is_a_violation():
    verdict = healthwait.evaluate(snapshot(penpot_valkey=("running", "")), elapsed=2, limit=LIMIT)

    assert verdict.kind == "failed"
    assert verdict.service == "penpot-valkey"
    assert "no health check" in verdict.message


def test_a_missing_service_is_pending_then_failed():
    partial = snapshot(penpot_mailpit=None)

    assert healthwait.evaluate(partial, elapsed=10, limit=LIMIT).kind == "pending"
    failed = healthwait.evaluate(partial, elapsed=LIMIT, limit=LIMIT)
    assert failed.kind == "failed" and failed.service == "penpot-mailpit"
    assert "not running" in failed.message


def test_an_empty_snapshot_is_pending_then_failed_naming_the_first_service():
    assert healthwait.evaluate([], elapsed=1, limit=LIMIT).kind == "pending"
    failed = healthwait.evaluate([], elapsed=LIMIT, limit=LIMIT)
    assert failed.kind == "failed" and failed.service == SERVICES[0]


def test_the_first_failing_service_in_stack_order_is_reported():
    both = snapshot(penpot_exporter=("exited", ""), penpot_backend=("exited", ""))

    assert healthwait.evaluate(both, elapsed=1, limit=LIMIT).service == "penpot-backend"


def test_a_restarting_service_is_pending_until_the_limit():
    flapping = snapshot(penpot_backend=("restarting", ""))

    assert healthwait.evaluate(flapping, elapsed=20, limit=LIMIT).kind == "pending"
    assert healthwait.evaluate(flapping, elapsed=LIMIT, limit=LIMIT).kind == "failed"


def test_evaluate_uses_no_clock_and_is_deterministic():
    entries = snapshot(penpot_backend=("running", "starting"))

    assert healthwait.evaluate(entries, 10, LIMIT) == healthwait.evaluate(entries, 10, LIMIT)


def test_parse_ps_reads_json_lines():
    text = "\n".join(json.dumps(entry) for entry in snapshot())

    assert len(healthwait.parse_ps(text)) == 8


def test_parse_ps_reads_a_json_array():
    assert len(healthwait.parse_ps(json.dumps(snapshot()))) == 8


@pytest.mark.parametrize("text", ["", "   \n", "null"])
def test_parse_ps_treats_empty_output_as_no_services(text):
    assert healthwait.parse_ps(text) == []


def test_format_status_lists_every_service_and_marks_missing_ones():
    table = healthwait.format_status(snapshot(penpot_mailpit=None, penpot_backend=("running", "starting")))

    lines = table.splitlines()
    assert lines[0].split() == ["SERVICE", "STATE", "HEALTH"]
    assert len(lines) == 1 + 8
    assert any(line.split() == ["penpot-backend", "running", "starting"] for line in lines)
    assert any(line.split()[:2] == ["penpot-mailpit", "not"] for line in lines)
