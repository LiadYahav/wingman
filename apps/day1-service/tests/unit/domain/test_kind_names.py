"""A seed's and a KV cluster's names, read by their kind (ADR-0067)."""

from __future__ import annotations

from wingman_day1.domain.cluster_delete import delete_confirm_problems, delete_summary
from wingman_day1.domain.kind_names import (
    describe_cluster_file,
    describe_hub,
    describe_kv_cluster,
    describe_seed,
)
from wingman_day1.domain.names import Env
from wingman_day1.domain.paths import ClusterRef


def test_a_seed_named_by_the_convention_follows_it_with_its_zone() -> None:
    seed = describe_seed("ocp4-prod-seed-bat-yam-az1-a", site="bat-yam")
    assert seed.follows_convention
    assert (seed.env, seed.zone, seed.letter) == (Env.PROD, "az1", "a")


def test_a_seed_named_as_the_deployed_workflows_find_one_is_flagged_with_its_zone() -> None:
    seed = describe_seed("ocp4-seed-five-az2", site="five")
    assert not seed.follows_convention
    assert (seed.env, seed.zone) == (None, "az2")
    assert "ocp4-<lc>-seed-five-<zone>-<id>" in seed.problems[0]


def test_a_seed_of_another_site_or_shape_does_not_follow() -> None:
    for name in ("ocp4-prod-seed-six-az1-a", "ocp4-prod-seed-five-a", "ocp4-prod-seed-five-az1-ab"):
        seed = describe_seed(name, site="five")
        assert not seed.follows_convention, name
        assert seed.zone is None, name


def test_a_kv_cluster_named_by_the_convention_follows_it() -> None:
    kv = describe_kv_cluster("ocp4-test-kv-five-az3-b", site="five")
    assert kv.follows_convention
    assert (kv.env, kv.short_name, kv.zone, kv.sequence) == (Env.TEST, "kv", "az3", "b")


def test_a_kv_cluster_named_by_the_deployed_workflows_is_flagged_with_its_zone() -> None:
    kv = describe_kv_cluster("ocp4-kubevirt-five-az1-1", site="five")
    assert not kv.follows_convention
    assert kv.zone == "az1"
    assert "ocp4-<lc>-kv-five-<zone>-<id>" in kv.problems[0]


def test_each_folder_and_file_is_read_by_its_kind() -> None:
    assert describe_hub("ocp4-prod-mce-five-a", site="five").follows_convention
    assert describe_hub("ocp4-prod-seed-five-az1-a", site="five").zone == "az1"
    tenant = describe_cluster_file(
        ClusterRef("five", "ocp4-prod-mce-five-a", "ocp4-prod-eck-five-a")
    )
    assert (tenant.short_name, tenant.zone) == ("eck", None)
    # In a seed's folder every file is a KV cluster, and is read as one
    stray = describe_cluster_file(ClusterRef("five", "ocp4-seed-five-az1", "ocp4-prod-eck-five-a"))
    assert not stray.follows_convention
    assert "KV cluster" in stray.problems[-1]


def test_only_a_kv_clusters_delete_asks_for_its_name_and_names_its_vms() -> None:
    kv = ClusterRef("five", "ocp4-prod-seed-five-az1-a", "ocp4-prod-kv-five-az1-a")
    tenant = ClusterRef("five", "ocp4-prod-mce-five-a", "ocp4-prod-eck-five-a")
    assert delete_confirm_problems(kv, "")
    assert delete_confirm_problems(kv, "ocp4-prod-kv-five-az1-b")
    assert delete_confirm_problems(kv, kv.name) == []
    assert delete_confirm_problems(tenant, "") == []
    assert "VM workers" in delete_summary(kv)
    assert "VM" not in delete_summary(tenant)
