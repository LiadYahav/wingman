"""The add-server workflow's run ids and who may have started a run (ADR-0057)."""

from __future__ import annotations

import pytest

from wingman_day1.domain.add_server import (
    AddServerRequest,
    Origin,
    RunTarget,
    canonical_mce,
    run_target,
)

MCE = "ocp4-prod-mce-site1-a"


def test_a_pool_draw_names_its_mce_infra_env_and_slot() -> None:
    target = run_target(f"add-server-to-mce-{MCE}_dell-r650-site1-96c-768gb_7")
    assert target == RunTarget(MCE, Origin.POOL, infra_env="dell-r650-site1-96c-768gb", slot=7)


def test_a_named_install_names_its_server_and_is_a_persons() -> None:
    target = run_target(f"add-server-to-mce-{MCE}_ocp-dell-r650-site1-96c-768gb-dlfake0811")
    assert target == RunTarget(MCE, Origin.NAMED, server="ocp-dell-r650-site1-96c-768gb-dlfake0811")


@pytest.mark.parametrize(
    "workflow_id",
    [
        "uninstall-server-from-hc-ocp-x",
        f"add-server-to-mce-{MCE}",
        f"add-server-to-mce-{MCE}_pool_0",
        f"add-server-to-mce-{MCE}_pool_101",
        f"add-server-to-mce-{MCE}_a_b_c_d",
        f"add-server-to-mce-{MCE}__3",
    ],
)
def test_any_other_id_says_nothing(workflow_id: str) -> None:
    assert run_target(workflow_id) is None


def test_the_orchestrator_adds_ocp4_to_an_mce() -> None:
    assert canonical_mce("prod-mce-site1-a") == MCE
    assert canonical_mce(MCE) == MCE


def test_a_request_knows_its_size() -> None:
    assert AddServerRequest(MCE, "p", None, count=3).size == 3
    assert AddServerRequest(MCE, "p", None, server_names=("a", "b")).size == 2
