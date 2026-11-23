"""herzi's marks on an InfraEnv: read as herzi writes them, malformed ones as none."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from wingman_day1.domain.herzi_marks import (
    BLOCKED_UNTIL,
    IGNORE_LABEL,
    PAUSED,
    STATE,
    HerziMarks,
    herzi_marks,
)
from wingman_day1.infrastructure.hub_objects import infra_env_from

FAILED = "2026-11-23T10:00:00.123456789Z"
"""Go's RFC 3339 with nanoseconds, as herzi's state encodes a time."""
AT_FAILURE = datetime(2026, 11, 23, 10, 0, 0, 123456, tzinfo=UTC)


def test_nothing_marked_is_none() -> None:
    marks = herzi_marks({}, {})
    assert marks == HerziMarks()
    assert not marks.any


def test_ignored_by_its_label_whatever_its_value_and_paused_only_by_true() -> None:
    assert herzi_marks({IGNORE_LABEL: ""}, {}).ignored
    assert herzi_marks({}, {PAUSED: "true"}).paused
    assert not herzi_marks({}, {PAUSED: "yes"}).paused


def test_an_order_in_flight_is_its_block_markers_deadline() -> None:
    marks = herzi_marks({}, {BLOCKED_UNTIL: "2026-11-23T10:05:00Z"})
    assert marks.blocked_until == datetime(2026, 11, 23, 10, 5, tzinfo=UTC)
    assert marks.any
    assert herzi_marks({}, {BLOCKED_UNTIL: "soon"}).blocked_until is None


@pytest.mark.parametrize(
    ("state", "since"),
    [
        (json.dumps({"capFailAt": FAILED}), AT_FAILURE),
        (json.dumps({"capFailAt": FAILED, "lastOKAt": "2026-11-23T09:00:00Z"}), AT_FAILURE),
        (json.dumps({"capFailAt": FAILED, "lastOKAt": "2026-11-23T11:00:00Z"}), None),
        (json.dumps({"capFailAt": "0001-01-01T00:00:00Z"}), None),
        (json.dumps({"lastOKAt": "2026-11-23T11:00:00Z"}), None),
        ("{", None),
        ("[]", None),
        (json.dumps({"capFailAt": FAILED, "pad": "x" * 1024}), None),
    ],
)
def test_no_hardware_is_a_capacity_failure_not_recovered_since(
    state: str, since: datetime | None
) -> None:
    assert herzi_marks({}, {STATE: state}).no_hardware_since == since


def test_the_adapter_reads_the_marks_from_the_infraenvs_metadata() -> None:
    raw = {
        "metadata": {
            "name": "r650-mtl-az1",
            "labels": {IGNORE_LABEL: "true"},
            "annotations": {PAUSED: "true", STATE: json.dumps({"capFailAt": FAILED})},
        },
        "spec": {"agentLabels": {"redbull.io/flavor": "r650"}},
    }
    found = infra_env_from(raw)
    assert found.agent_labels == {"redbull.io/flavor": "r650"}
    assert found.herzi == HerziMarks(ignored=True, paused=True, no_hardware_since=AT_FAILURE)
