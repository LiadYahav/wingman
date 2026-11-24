"""The kinds of MCE folder and cluster file, by the platform's naming convention (ADR-0067)."""

from __future__ import annotations

import pytest

from wingman_core.domain.cluster_kinds import (
    HostedClusterKind,
    MceKind,
    hosted_cluster_kind,
    is_kv_name,
    mce_kind,
)


@pytest.mark.parametrize(
    "folder",
    [
        "ocp4-prod-seed-five-az1-a",  # the convention
        "ocp4-test-seed-bat-yam-az3-b",  # a site with a dash
        "ocp4-seed-five-az1",  # what the deployed workflows look for
        "ocp4-prep-seed-five-a",  # workflows PR #26's redesign: still a seed by its word
    ],
)
def test_a_folder_with_the_reserved_word_seed_is_a_seed(folder: str) -> None:
    assert mce_kind(folder) is MceKind.SEED


@pytest.mark.parametrize(
    "folder",
    [
        "ocp4-prod-mce-five-a",
        "ocp4-mce-workflow-test",  # off-convention, still a tenant's hub
        "ocp4-prod-mce-seed-a",  # 'seed' is not the flavor here
        "ocp4-prod-seedling-five-a",  # a word that starts with seed is not the word
        "ocp4-dev-seed-five-az1-a",  # 'dev' is no lifecycle: not the convention's seed
        "seed-five-az1",
    ],
)
def test_any_other_folder_is_a_customer_mce(folder: str) -> None:
    assert mce_kind(folder) is MceKind.MCE


@pytest.mark.parametrize(
    "stem",
    [
        "ocp4-prod-kv-five-az1-a",  # the convention
        "ocp4-kv-five-az1-a",
        "ocp4-kubevirt-five-az1",  # the deployed workflows' prefix
        "ocp4-kubevirt-five-az1-1",
    ],
)
def test_a_name_with_the_reserved_word_kv_is_a_kv_cluster_anywhere(stem: str) -> None:
    assert is_kv_name(stem)
    assert hosted_cluster_kind(stem, mce="ocp4-prod-mce-five-a") is HostedClusterKind.KV
    assert hosted_cluster_kind(stem, mce="") is HostedClusterKind.KV


@pytest.mark.parametrize(
    "stem",
    [
        "ocp4-prod-eck-five-a",
        "ocp4-prod-kvm-five-a",  # a flavor that starts with kv is not the word
        "ocp4-prod-kubevirt-five-a",  # 'kubevirt' as a tenant's flavor: not reserved
        "ocp4-upgrade-demo",
    ],
)
def test_a_tenant_name_under_a_customer_mce_is_a_tenant(stem: str) -> None:
    assert not is_kv_name(stem)
    assert hosted_cluster_kind(stem, mce="ocp4-prod-mce-five-a") is HostedClusterKind.TENANT


def test_every_file_in_a_seed_folder_is_a_kv_cluster_as_the_workflows_list_them() -> None:
    assert hosted_cluster_kind("anything", mce="ocp4-seed-five-az1") is HostedClusterKind.KV
    assert hosted_cluster_kind("ocp4-prod-eck-five-a", mce="ocp4-prod-seed-five-az1-a") is (
        HostedClusterKind.KV
    )
