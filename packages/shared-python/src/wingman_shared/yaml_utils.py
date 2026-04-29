"""YAML utilities using ruamel.yaml for round-trip fidelity.

Key behaviors:
- Multi-document YAML (--- separated) handled natively
- Deep merge: dicts merge recursively, LISTS ARE FULLY REPLACED (Helm semantics)
- Normalize: parse + re-serialize to strip formatting noise before diffing
"""

from __future__ import annotations

import io
from copy import deepcopy
from typing import Any

from ruamel.yaml import YAML


def _make_yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096  # prevent unwanted line wrapping
    y.indent(sequence=4, offset=2)  # standard YAML list indentation
    y.default_flow_style = False  # always use block style, not inline
    y.allow_duplicate_keys = True  # silently keep last value; avoids crash on real-world Helm files
    return y


def parse_multi_document(content: str) -> list[Any]:
    """Parse a YAML string into a list of dicts.

    Handles both single-document (no ---) and multi-document (--- separated) files.
    ruamel's load_all raises ComposerError on plain YAML files without --- markers,
    so we detect which format is in use and dispatch accordingly.

    Returns empty list on invalid YAML rather than raising - callers can check
    if len(result) == 0 and log warnings as needed.
    """
    try:
        y = _make_yaml()
        stripped = content.strip()
        if not stripped:
            return []
        if "---" not in stripped:
            # Single document — load_all would raise ComposerError here
            result = y.load(stripped)
            return [result] if result is not None else []
        return [d for d in y.load_all(stripped) if d is not None]
    except Exception:
        # Invalid YAML - return empty list, let callers handle
        return []


def dump_multi_document(docs: list[Any]) -> str:
    """Serialize a list of dicts to a multi-document YAML string."""
    y = _make_yaml()
    y.explicit_start = True
    stream = io.StringIO()
    y.dump_all(docs, stream)
    return stream.getvalue()


def parse_single(content: str) -> Any:
    """Parse a single-document YAML string. Returns None on invalid YAML."""
    try:
        y = _make_yaml()
        return y.load(content)
    except Exception:
        return None


def dump_single(data: Any) -> str:
    """Serialize a single dict to YAML."""
    y = _make_yaml()
    stream = io.StringIO()
    y.dump(data, stream)
    return stream.getvalue()


def normalize_yaml(content: str) -> str:
    """Parse and re-serialize to canonical form for diffing.

    Strips formatting differences (extra spaces, different quote styles, etc.)
    so that structural diffs are not polluted by formatting noise.
    """
    y = YAML()
    y.default_flow_style = False
    data = y.load(content)
    stream = io.StringIO()
    y.dump(data, stream)
    return stream.getvalue()


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dicts with Helm/YAML list-replacement semantics.

    Rules:
    - Dicts: merged recursively (override keys win)
    - Lists: override FULLY REPLACES base (no append/merge)
    - Scalars: override wins
    - None values in override: removes the key from result

    This matches Helm's values.yaml merge behavior.

    Example:
        base     = {"ports": [80, 443], "image": {"tag": "v1"}}
        override = {"ports": [8080],    "image": {"repo": "myrepo"}}
        result   = {"ports": [8080],    "image": {"tag": "v1", "repo": "myrepo"}}
    """
    result: dict[str, Any] = deepcopy(base)
    for key, value in override.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            # Scalars AND lists: override wins entirely
            result[key] = deepcopy(value)
    return result


def merge_three_layers(
    chart_values: dict[str, Any],
    team_values: dict[str, Any],
    cluster_values: dict[str, Any],
) -> dict[str, Any]:
    """Merge three priority layers: chart < team < cluster.

    Args:
        chart_values: Helm chart's default values.yaml (lowest priority)
        team_values: Team's default values override (middle priority)
        cluster_values: Cluster-specific override (highest priority)

    Returns:
        Final merged values dict
    """
    merged = deep_merge(chart_values, team_values)
    return deep_merge(merged, cluster_values)


def compute_provenance(
    chart_values: dict[str, Any],
    team_values: dict[str, Any],
    cluster_values: dict[str, Any],
) -> dict[str, Any]:
    """Build a provenance map showing which layer each key came from.

    Returns a dict with same structure as merged values, but values are
    "chart" | "team" | "cluster" indicating which layer set the value.
    Used by the frontend merge preview UI.
    """
    merged_ct = deep_merge(chart_values, team_values)
    merged_all = deep_merge(merged_ct, cluster_values)
    return _trace_provenance(merged_all, chart_values, team_values, cluster_values)


def _trace_provenance(
    merged: dict[str, Any],
    chart: dict[str, Any],
    team: dict[str, Any],
    cluster: dict[str, Any],
    path: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in merged.items():
        full_path = f"{path}.{key}" if path else key
        if isinstance(value, dict):
            result[key] = _trace_provenance(
                value,
                chart.get(key, {}) if isinstance(chart.get(key), dict) else {},
                team.get(key, {}) if isinstance(team.get(key), dict) else {},
                cluster.get(key, {}) if isinstance(cluster.get(key), dict) else {},
                full_path,
            )
        else:
            if key in cluster and cluster[key] == value:
                result[key] = "cluster"
            elif key in team and team[key] == value:
                result[key] = "team"
            else:
                result[key] = "chart"
    return result
