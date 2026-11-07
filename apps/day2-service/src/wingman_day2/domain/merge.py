"""Helm's value merge, with provenance: which layer set each value (ADR-0021).

Helm does it in two steps, and the result differs from a naive left fold when
a layer sets ``null``:

1. The ``-f`` files are merged in order (``mergeMaps``): maps merge key by
   key, anything else replaces, and ``null`` is kept as an explicit value.
2. The result is coalesced onto the chart's own ``values.yaml``
   (``coalesceValues``): a ``null`` deletes the key, chart defaults fill the
   rest, and maps merge recursively.

Provenance has the shape of the merged values; each leaf is the label of the
layer that set it (an empty map is labelled as a leaf).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

type Values = dict[str, object]
type Provenance = dict[str, object]


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Merged values and, in the same shape, the layer label of every leaf."""

    values: Values
    provenance: Provenance


def _copy(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(k): _copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy(v) for v in value]
    return value


def _labels(value: object, label: str) -> object:
    if isinstance(value, Mapping) and value:
        return {str(k): _labels(v, label) for k, v in value.items()}
    return label


def _merge_maps(
    values: Values, provenance: Provenance, over: Mapping[str, object], label: str
) -> tuple[Values, Provenance]:
    out_values, out_prov = dict(values), dict(provenance)
    for key, value in over.items():
        current = out_values.get(key)
        if isinstance(value, Mapping) and isinstance(current, dict):
            sub_prov = out_prov.get(key)
            out_values[key], out_prov[key] = _merge_maps(
                current, sub_prov if isinstance(sub_prov, dict) else {}, value, label
            )
            if not out_values[key]:
                out_prov[key] = label
        else:
            out_values[key] = _copy(value)
            out_prov[key] = _labels(value, label)
    return out_values, out_prov


def _any_label(provenance: object) -> str:
    if isinstance(provenance, dict):
        return next((_any_label(p) for p in provenance.values()), "")
    return provenance if isinstance(provenance, str) else ""


def _without_nulls(value: object, provenance: object) -> tuple[object, object]:
    if not isinstance(value, dict):
        return value, provenance
    prov = provenance if isinstance(provenance, dict) else {}
    out_values: Values = {}
    out_prov: Provenance = {}
    for key, sub in value.items():
        if sub is None:
            continue
        out_values[key], out_prov[key] = _without_nulls(sub, prov.get(key, provenance))
    return out_values, (out_prov if out_values else _any_label(provenance))


def _coalesce(
    user: Values, user_prov: Provenance, chart: Mapping[str, object], chart_label: str
) -> tuple[Values, Provenance]:
    out_values: Values = {}
    out_prov: Provenance = {}
    for key in [*chart, *(k for k in user if k not in chart)]:
        if key not in user:
            default = chart[key]
            if default is not None:
                out_values[key], out_prov[key] = _without_nulls(
                    _copy(default), _labels(default, chart_label)
                )
            continue
        value = user[key]
        if value is None:
            continue
        default = chart.get(key)
        if isinstance(value, dict) and isinstance(default, Mapping):
            sub_prov = user_prov.get(key)
            merged, prov = _coalesce(
                value, sub_prov if isinstance(sub_prov, dict) else {}, default, chart_label
            )
            out_values[key] = merged
            out_prov[key] = prov if merged else (_any_label(user_prov.get(key)) or chart_label)
        else:
            out_values[key], out_prov[key] = _without_nulls(value, user_prov.get(key))
    return out_values, out_prov


def merge_values(
    chart_defaults: Mapping[str, object],
    layers: Sequence[tuple[str, Mapping[str, object]]],
    *,
    chart_label: str = "chart",
) -> MergeResult:
    """What Helm makes of the chart's ``values.yaml`` plus ``-f`` ``layers`` (label, values)."""
    user: Values = {}
    user_prov: Provenance = {}
    for label, values in layers:
        user, user_prov = _merge_maps(user, user_prov, values, label)
    merged, provenance = _coalesce(user, user_prov, chart_defaults, chart_label)
    return MergeResult(merged, provenance)
