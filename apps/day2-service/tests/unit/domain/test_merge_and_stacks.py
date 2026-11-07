"""Helm's merge with provenance, the value stacks per kind, and exclusions."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wingman_day2.domain.clusters import ClusterRef
from wingman_day2.domain.exclusions import Exclusions, platform_exclusions
from wingman_day2.domain.merge import merge_values
from wingman_day2.domain.stacks import Layer, LayerRole, deploy_config_layers, workload_layers

# ── merge ───────────────────────────────────────────────────────────────────


def test_maps_merge_lists_and_scalars_replace_later_wins() -> None:
    result = merge_values(
        {"image": {"repo": "r", "tag": "1"}, "args": ["a"], "replicas": 1},
        [("team", {"image": {"tag": "2"}, "args": ["b"]}), ("cluster", {"replicas": 3})],
    )
    assert result.values == {"image": {"repo": "r", "tag": "2"}, "args": ["b"], "replicas": 3}
    assert result.provenance == {
        "image": {"repo": "chart", "tag": "team"},
        "args": "team",
        "replicas": "cluster",
    }


def test_null_deletes_a_chart_default() -> None:
    result = merge_values(
        {"a": 1, "b": {"c": 1, "d": 2}}, [("cluster", {"a": None, "b": {"c": None}})]
    )
    assert result.values == {"b": {"d": 2}}
    assert result.provenance == {"b": {"d": "chart"}}


def test_user_files_merge_before_the_chart_defaults_like_helm() -> None:
    # Helm merges the -f files first (null kept), then coalesces onto the chart: a later
    # map re-adds the key, and the chart's other sub-keys survive.
    result = merge_values({"a": {"x": 1}}, [("team", {"a": None}), ("cluster", {"a": {"y": 2}})])
    assert result.values == {"a": {"x": 1, "y": 2}}
    assert result.provenance == {"a": {"x": "chart", "y": "cluster"}}


def test_a_scalar_replaces_a_map_and_back() -> None:
    result = merge_values({"a": {"x": 1}}, [("team", {"a": "flat"})])
    assert (result.values, result.provenance) == ({"a": "flat"}, {"a": "team"})
    result = merge_values({"a": 1}, [("team", {"a": {"x": 1}})])
    assert (result.values, result.provenance) == ({"a": {"x": 1}}, {"a": {"x": "team"}})


def test_empty_maps_are_labelled_as_leaves() -> None:
    result = merge_values({}, [("team", {"a": {}}), ("cluster", {"b": {"c": None}})])
    assert result.values == {"a": {}, "b": {}}
    assert result.provenance == {"a": "team", "b": "cluster"}


def test_merging_into_an_empty_map_and_deleting_everything() -> None:
    result = merge_values({"a": {}}, [("team", {"a": {"x": 1}})])
    assert result.provenance == {"a": {"x": "team"}}
    result = merge_values({"a": {"x": 1}}, [("team", {"a": {"x": None}})])
    assert result.values == {"a": {}} and result.provenance == {"a": "team"}
    result = merge_values({"a": {"x": 1}}, [("t", {"a": {}}), ("u", {"a": {}})])
    assert result.provenance == {"a": {"x": "chart"}}


def test_a_null_chart_default_is_absent() -> None:
    assert merge_values({"a": None, "b": {"c": None, "d": 1}}, []).values == {"b": {"d": 1}}


scalars = st.one_of(st.integers(-3, 3), st.sampled_from(["x", "y"]), st.booleans(), st.none())
keys = st.sampled_from(["a", "b", "c"])
trees = st.recursive(scalars, lambda inner: st.dictionaries(keys, inner, max_size=3), max_leaves=8)
layer_maps = st.dictionaries(keys, trees, max_size=3)


def _leaves(values: object, provenance: object, path: tuple[str, ...] = ()):  # noqa: ANN202
    if isinstance(values, dict) and (values or not path):
        assert isinstance(provenance, dict), path
        for key, sub in values.items():
            yield from _leaves(sub, provenance[key], (*path, key))
    else:
        assert isinstance(provenance, str), path
        yield path, values, provenance


def _at(values: Mapping[str, object], path: tuple[str, ...]) -> object:
    current: object = values
    for key in path:
        assert isinstance(current, Mapping)
        current = current[key]
    return current


@given(layer_maps, st.lists(layer_maps, max_size=4))
def test_provenance_is_truthful(chart: dict[str, object], layers: list[dict[str, object]]) -> None:
    labelled = [(f"L{i}", values) for i, values in enumerate(layers)]
    result = merge_values(chart, labelled)
    sources = dict(labelled) | {"chart": chart}
    for path, value, label in _leaves(result.values, result.provenance):
        if isinstance(value, dict):
            continue  # an empty map can be the residue of several layers
        assert _at(sources[label], path) == value, (path, label)


@given(layer_maps, st.lists(layer_maps, max_size=3))
def test_merged_values_never_hold_null(
    chart: dict[str, object], layers: list[dict[str, object]]
) -> None:
    result = merge_values(chart, [(str(i), v) for i, v in enumerate(layers)])
    for _, value, _ in _leaves(result.values, result.provenance):
        assert value is not None


@given(layer_maps)
def test_an_empty_layer_changes_nothing(chart: dict[str, object]) -> None:
    assert merge_values(chart, [("x", {})]) == merge_values(chart, [])


# ── stacks ──────────────────────────────────────────────────────────────────


def _paths(layers: tuple[Layer, ...]) -> list[str]:
    return [str(layer.path) for layer in layers]


def test_hosted_cluster_workload_stack_is_the_ten_layers_of_deploy_app_yaml() -> None:
    ref = ClusterRef.hosted("site1", "prod", "mce1", "hc1")
    assert _paths(workload_layers(ref, "c", "4.16.27")) == [
        "operators/c/values.yaml",
        "operators/c/ocp-versions/4.16.27/values.yaml",
        "sites/site1/values.yaml",
        "sites/site1/prod/values.yaml",
        "defaults/hosted-clusters/c/values.yaml",
        "defaults/hosted-clusters/c/values-prod.yaml",
        "defaults/hosted-clusters/c/values-hc1.yaml",
        "sites/site1/prod/mces/mce1/values.yaml",
        "sites/site1/prod/mces/mce1/hc1/values.yaml",
        "sites/site1/prod/mces/mce1/hc1/c/values.yaml",
    ]
    assert [layer.role for layer in workload_layers(ref, "c", None)][0:2] == [
        LayerRole.TEAM,
        LayerRole.SITE,
    ]


def test_mce_upi_and_hub_stacks() -> None:
    mce = ClusterRef.mce_hub("site1", "prep", "m")
    assert _paths(workload_layers(mce, "c", None))[3:] == [
        "defaults/mces/c/values.yaml",
        "defaults/mces/c/values-prep.yaml",
        "defaults/mces/c/values-m.yaml",
        "sites/site1/prep/mces/m/values.yaml",
        "sites/site1/prep/mces/m/in-cluster/values.yaml",
        "sites/site1/prep/mces/m/in-cluster/c/values.yaml",
    ]
    upi = ClusterRef.upi("site1", "prod", "u")
    assert _paths(workload_layers(upi, "c", None))[3:] == [
        "defaults/upi/c/values.yaml",
        "defaults/upi/c/values-prod.yaml",
        "defaults/upi/c/values-u.yaml",
        "sites/site1/prod/upi/values.yaml",
        "sites/site1/prod/upi/u/values.yaml",
        "sites/site1/prod/upi/u/c/values.yaml",
    ]
    assert _paths(workload_layers(ClusterRef.hub(), "c", None)) == [
        "defaults/hub/values.yaml",
        "operators/c/values.yaml",
        "defaults/hub/c/values.yaml",
    ]


def test_deploy_config_stacks() -> None:
    ref = ClusterRef.hosted("site1", "prod", "m", "hc")
    assert _paths(deploy_config_layers(ref, "c", "4.16.27")) == [
        "operators/c/c.yaml",
        "operators/c/ocp-versions/4.16.27/c.yaml",
        "defaults/hosted-clusters/c/c.yaml",
        "sites/site1/prod/mces/m/hc/c/c.yaml",
    ]
    assert _paths(deploy_config_layers(ClusterRef.hub(), "c", None)) == [
        "operators/c/c.yaml",
        "defaults/hub/c/c.yaml",
    ]


# ── exclusions ──────────────────────────────────────────────────────────────


def test_exclusions_as_the_operators_chart_reads_them() -> None:
    assert platform_exclusions(None) == Exclusions()
    assert platform_exclusions({"exclusions": None}) == Exclusions()
    parsed = platform_exclusions({"exclusions": {"a": ["m1", "m2"], "b": None, "c": []}})
    assert parsed == Exclusions({"a": ("m1", "m2")})
    assert parsed is not None and parsed.excluded_charts("m2") == {"a"}


@pytest.mark.parametrize("doc", [["a"], {"exclusions": ["a"]}, {"exclusions": {"a": "m1"}}, "text"])
def test_exclusions_the_template_fails_on(doc: object) -> None:
    assert platform_exclusions(doc) is None
