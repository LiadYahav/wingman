"""Who owns a cluster's versions while upgrades are on (ADR-0055, amending ADR-0012).

With ``DAY1_UPGRADES`` on, ``mastertag``, every ``workertag`` and
``pausedUntil`` are the upgrade workflow's: an edit may not change them,
except to remove ``pausedUntil`` after an aborted upgrade. With it off,
nothing changes.
"""

from __future__ import annotations

import pytest

from wingman_day1.domain.cluster_file import edit_problems
from wingman_day1.domain.upgrades import (
    VERSIONS_BY_UPGRADE,
    UpgradeDecision,
    upgrade_workflow_id,
    version_problems,
)

FILE = """owner:
  merkaz: "1"
mastertag: 4.18.22-x86_64
nodepool:
- name: zone-a
  infraEnvName: dell
  replicas: 3
  workertag: 4.18.22-x86_64
- infraEnvName: hp
  replicas: 2
"""
ABORTED = FILE + 'pausedUntil: "true"\n'


def problems(edited: str, current: str = FILE) -> list[str]:
    return edit_problems(current, edited, versions_by_workflow=True)


def test_the_run_id_is_the_file_stem_with_the_workflows_prefix() -> None:
    assert upgrade_workflow_id("ocp4-prod-lark-site1") == "upgrade-cluster-ocp4-prod-lark-site1"


def test_abort_and_admin_ack_need_a_reason_and_continue_takes_none() -> None:
    assert {d for d in UpgradeDecision if d.needs_reason} == {
        UpgradeDecision.ABORT,
        UpgradeDecision.APPROVE_ADMIN_ACK,
    }
    assert {d for d in UpgradeDecision if not d.takes_reason} == {UpgradeDecision.CONTINUE}


@pytest.mark.parametrize(
    ("old", "new", "key"),
    [
        ("mastertag: 4.18.22-x86_64", "mastertag: 4.18.56-x86_64", "mastertag"),
        ("mastertag: 4.18.22-x86_64", "mastertag: 4.18.22-x86_64\nworkertag: 4.18.22", "workertag"),
        ("  workertag: 4.18.22-x86_64\n", "  workertag: 4.17.58-x86_64\n", "nodepool zone-a"),
        ("  workertag: 4.18.22-x86_64\n", "", "nodepool zone-a"),
        ("- infraEnvName: hp\n", "- infraEnvName: hp\n  workertag: 4.18.22\n", "nodepool hp"),
    ],
)
def test_changing_a_version_is_refused_with_the_reason(old: str, new: str, key: str) -> None:
    found = problems(FILE.replace(old, new))
    assert found == [
        f"{key}{' workertag' if key.startswith('nodepool') else ''}: {VERSIONS_BY_UPGRADE}"
    ]


def test_adding_or_changing_paused_until_is_refused_and_removing_it_is_not() -> None:
    added = problems(ABORTED)
    assert len(added) == 1 and added[0].startswith("pausedUntil: ")
    assert added[0].endswith(VERSIONS_BY_UPGRADE)
    assert problems(ABORTED.replace('"true"', '"2026-12-01T00:00:00Z"'), current=ABORTED)
    assert problems(FILE, current=ABORTED) == [], "a person clears it after an aborted upgrade"
    assert problems(ABORTED.replace("replicas: 3", "replicas: 4"), current=ABORTED) == []


def test_everything_else_and_a_new_pool_at_the_cluster_version_stay_editable() -> None:
    assert problems(FILE.replace("replicas: 3", "replicas: 5")) == []
    new_pool = "- infraEnvName: cisco\n  replicas: 1\n  workertag: 4.18.22-x86_64\n"
    assert problems(FILE + new_pool) == []
    assert problems(FILE + new_pool.replace("4.18.22-x86_64", "4.18.22")) == []
    assert problems(FILE + "- infraEnvName: cisco\n  replicas: 1\n") == []
    removed = FILE.replace("- infraEnvName: hp\n  replicas: 2\n", "")
    assert problems(removed) == [], "removing a NodePool is not a version change"


def test_a_new_pool_at_another_version_is_refused() -> None:
    new_pool = "- infraEnvName: cisco\n  replicas: 1\n  workertag: 4.17.58-x86_64\n"
    assert problems(FILE + new_pool) == [f"nodepool cisco workertag: {VERSIONS_BY_UPGRADE}"]


def test_with_upgrades_off_versions_are_a_normal_edit() -> None:
    edited = FILE.replace("4.18.22-x86_64", "4.18.56-x86_64")
    assert edit_problems(FILE, edited) == []
    assert edit_problems(FILE, ABORTED) == []


def test_the_rule_reads_parsed_values_and_ignores_unreadable_pools() -> None:
    old = {"mastertag": "4.18.22", "nodepool": ["not a pool", {"name": "a", "workertag": "1"}]}
    assert version_problems(old, dict(old)) == []
    assert version_problems({"nodepool": "nonsense"}, {"nodepool": None}) == []
