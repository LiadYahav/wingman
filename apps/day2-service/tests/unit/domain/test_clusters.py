"""Cluster identity: the four kinds, their ids, and what each implies for Argo and defaults."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wingman_day2.domain import layout
from wingman_day2.domain.clusters import (
    ClusterKind,
    ClusterRef,
    DefaultsScope,
    env_from_name,
)
from wingman_day2.domain.errors import ChangeRefusedError, InvalidClusterIdError

names = st.from_regex(r"[a-z0-9][a-z0-9-]{0,20}", fullmatch=True).filter(
    lambda n: n != "in-cluster"
)
envs = st.sampled_from(["prod", "prep", "test", "staging"])


@st.composite
def refs(draw: st.DrawFn) -> ClusterRef:
    kind = draw(st.sampled_from(list(ClusterKind)))
    if kind is ClusterKind.HUB:
        return ClusterRef.hub()
    site, env, name = draw(names), draw(envs), draw(names)
    if kind is ClusterKind.MCE:
        return ClusterRef.mce_hub(site, env, name)
    if kind is ClusterKind.HOSTED:
        return ClusterRef.hosted(site, env, draw(names), name)
    return ClusterRef.upi(site, env, name)


@given(refs())
def test_every_id_parses_back_to_its_ref(ref: ClusterRef) -> None:
    assert ClusterRef.parse(ref.id) == ref
    assert ":" not in ref.name


def test_ids_carry_kind_site_env_and_mce() -> None:
    assert ClusterRef.hub().id == "hub"
    assert ClusterRef.mce_hub("site1", "prod", "m").id == "mce:site1:prod:m"
    assert ClusterRef.hosted("site1", "prod", "m", "c").id == "hosted:site1:prod:m:c"
    assert ClusterRef.upi("site1", "prep", "u").id == "upi:site1:prep:u"


def test_a_day1_cluster_with_unknown_env_keeps_an_empty_env_in_its_id() -> None:
    ref = ClusterRef.parse("hosted:site1::ocp4-mce-workflow-test:ocp4-upgrade-demo")
    assert (ref.env, ref.mce, ref.name) == ("", "ocp4-mce-workflow-test", "ocp4-upgrade-demo")
    with pytest.raises(ChangeRefusedError):
        layout.cluster_dir(ref)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hub:x",
        "mce:a:b",
        "hosted:a:b:c",
        "upi:a:b:c:d",
        "nope:a:b:c",
        "hosted:a:b:c:..",
        "hosted:a:b:c:x/y",
        "hosted:a:b:c:in-cluster",
        "upi:a:prod:in-cluster",
        "upi:a::u",
        "hosted:a:b:c:.hidden",
    ],
)
def test_malformed_ids_are_refused(text: str) -> None:
    with pytest.raises(InvalidClusterIdError):
        ClusterRef.parse(text)


def test_shapes_are_enforced_when_building_directly() -> None:
    with pytest.raises(InvalidClusterIdError):
        ClusterRef(ClusterKind.HUB, "other")
    with pytest.raises(InvalidClusterIdError):
        ClusterRef(ClusterKind.HUB, "prod-hub", site="s")
    with pytest.raises(InvalidClusterIdError):
        ClusterRef(ClusterKind.MCE, "a", site="s", env="prod", mce="b")
    with pytest.raises(InvalidClusterIdError):
        ClusterRef(ClusterKind.UPI, "u", site="s", env="prod", mce="m")


@pytest.mark.parametrize(
    ("ref", "argo_cluster", "argo", "scope", "key"),
    [
        (ClusterRef.hub(), "in-cluster", "prod-hub", DefaultsScope.HUB, None),
        (ClusterRef.mce_hub("s", "prod", "m"), "in-cluster", "m", DefaultsScope.MCES, "m"),
        (
            ClusterRef.hosted("s", "prod", "m", "c"),
            "c",
            "m",
            DefaultsScope.HOSTED_CLUSTERS,
            "c",
        ),
        (ClusterRef.upi("s", "prod", "u"), "u", "prod-hub-upi", DefaultsScope.UPI, "u"),
    ],
)
def test_each_kind_maps_to_its_argo_and_fleet_scope(
    ref: ClusterRef, argo_cluster: str, argo: str, scope: DefaultsScope, key: str | None
) -> None:
    assert (ref.argo_cluster, ref.argo_instance, ref.defaults_scope, ref.exclusion_key) == (
        argo_cluster,
        argo,
        scope,
        key,
    )
    assert str(ref) == ref.id


def test_only_prod_prep_and_test_are_allowed_envs() -> None:
    assert ClusterRef.hosted("s", "prep", "m", "c").env_allowed
    assert not ClusterRef.hosted("s", "staging", "m", "c").env_allowed
    assert ClusterRef.hub().env_allowed


@pytest.mark.parametrize(
    ("name", "env"),
    [
        ("ocp4-prod-herzi-site1", "prod"),
        ("ocp4-prep-mce-site1-a", "prep"),
        ("ocp4-test-x-site2", "test"),
        ("ocp4-mce-workflow-test", ""),
        ("ocp4-upgrade-demo", ""),
        ("ocp4-dok-site1", ""),
        ("prod-x", ""),
    ],
)
def test_the_naming_convention_carries_the_env(name: str, env: str) -> None:
    assert env_from_name(name) == env


def test_folders_per_kind() -> None:
    assert str(layout.cluster_dir(ClusterRef.hub())) == "defaults/hub"
    mce = ClusterRef.mce_hub("site1", "prod", "m")
    assert str(layout.cluster_dir(mce)) == "sites/site1/prod/mces/m/in-cluster"
    assert str(layout.registration_dir(mce)) == "sites/site1/prod/mces/m"
    hosted = ClusterRef.hosted("site1", "prod", "m", "c")
    assert str(layout.chart_dir(hosted, "x")) == "sites/site1/prod/mces/m/c/x"
    assert str(layout.registration_dir(hosted)) == "sites/site1/prod/mces/m/c"
    upi = ClusterRef.upi("site1", "prod", "u")
    assert str(layout.cluster_dir(upi)) == "sites/site1/prod/upi/u"
    assert str(layout.upi_version_file(upi)) == "sites/site1/prod/upi/u/version.yaml"
    assert layout.registration_dir(ClusterRef.hub()) is None
    assert str(layout.day1_hosted_cluster_file("site1", "m", "c")) == (
        "sites/site1/mces/m/hostedClusters/c.yaml"
    )
