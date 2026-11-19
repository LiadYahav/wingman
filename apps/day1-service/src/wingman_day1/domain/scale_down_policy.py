"""A NodePool's scale-down policy: which servers a scale-down removes first (ADR-0062).

update-nodepool ranks a shrinking NodePool's Machines by a policy and marks the
first ones before it lowers the replicas, so CAPI removes exactly those. The
policy is, in this order (the workflow's rule):

1. the run's own ``scale_down_policy``, for that run only;
2. the NodePool's ``redbull.io/scale-down-policy``, which the
   hostedclusters-setup chart renders from the ``nodepool[]`` entry's
   ``annotations`` map, as written, after its own ``argocd.argoproj.io/sync-wave``;
3. none: nothing is marked, and CAPI picks at random.

Under every policy, Machines CAPI counts unhealthy go first, then Nodes that
are missing, NotReady or cordoned. The values are the workflow's
``ScaleDownPolicy``, and it refuses any other:

- ``fewest-pods``: the fewest workload pods, the least for the drain to move;
- ``least-requested``: the lowest share of CPU or memory its pods request;
- ``least-utilized``: the lowest live CPU or memory use, read from the hosted
  cluster's metrics API (``metrics.k8s.io``); without one the run fails
  (``NodeMetricsUnavailableError``).

A cluster file declares a NodePool's own policy as that annotation. Wingman
writes it at create from the template input ``nodepools[].scale_down_policy``
(none writes nothing: the platform default). A flavor may preset or lock it
(ADR-0026), and an edit may set it only to a policy the workflow knows, and
may not give an entry the sync-wave annotation the chart writes itself. A
specs-project template that does not render the input is refused, as for
image mirrors (ADR-0063): at a flavor save that gives it, and at a create
whose rendered file does not hold it as given.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Final, cast

from wingman_day1.domain.errors import RenderError
from wingman_day1.domain.nodepool_infra_envs import nodepool_entries
from wingman_day1.domain.template import analyze_template

SCALE_DOWN_POLICY: Final = "redbull.io/scale-down-policy"
SYNC_WAVE: Final = "argocd.argoproj.io/sync-wave"
"""The chart's own NodePool annotation: an entry's ``annotations`` never set it."""
"""The key update-nodepool reads off a NodePool to choose the servers a scale-down removes."""
ANNOTATIONS: Final = "annotations"
"""The ``nodepool[]`` entry's map the chart renders onto its NodePool."""
FILE_KEY: Final = (ANNOTATIONS, SCALE_DOWN_POLICY)
"""Where a ``nodepool[]`` entry holds its policy."""
INPUT: Final = "scale_down_policy"
"""The template input, in each ``nodepools[]`` entry; also the per-run override's field."""
GUIDE: Final = "docs/upgrade/3.48-to-3.49.md"
_LOCK = re.compile(rf"nodepools\[(\d+)\]\.{INPUT}")


class ScaleDownPolicy(StrEnum):
    """The policies update-nodepool knows (its ``ScaleDownPolicy``)."""

    FEWEST_PODS = "fewest-pods"
    LEAST_REQUESTED = "least-requested"
    LEAST_UTILIZED = "least-utilized"


POLICIES: Final = tuple(p.value for p in ScaleDownPolicy)
_KNOWN: Final = "fewest-pods, least-requested or least-utilized"


def policy_of(entry: Mapping[str, object]) -> str | None:
    """The policy a file entry's ``annotations`` name, as written; ``None`` without one.

    The chart renders an entry's annotations onto its NodePool, where
    update-nodepool reads the key (a label or an annotation set by hand on
    the MCE is read there too; the file cannot show it). The value is not
    checked here: the workflow refuses one it does not know.
    """
    annotations = entry.get(ANNOTATIONS)
    if not isinstance(annotations, Mapping):
        return None
    value = cast("Mapping[str, object]", annotations).get(SCALE_DOWN_POLICY)
    return None if value is None else str(value)


def value_problems(where: str, value: object, *, otherwise: str) -> list[str]:
    """Why ``value`` is not a policy the workflow knows; empty when it is."""
    if isinstance(value, str) and value in POLICIES:
        return []
    shown = repr(value) if isinstance(value, str) else f"{value!r} (not text)"
    return [
        f"{where}: {shown} is not a scale-down policy update-nodepool knows; use {_KNOWN}, "
        f"{otherwise}"
    ]


def chosen(pool: Mapping[str, object]) -> object:
    """A nodepool input's policy; ``None`` for none (left out, ``null`` or empty)."""
    value = pool.get(INPUT)
    return None if value in (None, "") else value


# ── Create and flavor save: the template input ──────────────────────────────


def input_problems(inputs: Mapping[str, object]) -> list[str]:
    """Each nodepool whose ``scale_down_policy`` is not a policy the workflow knows."""
    problems: list[str] = []
    for index, pool in nodepool_entries(inputs, "nodepools"):
        value = chosen(pool)
        if value is not None:
            where = f"nodepools[{index}].{INPUT}"
            problems += value_problems(where, value, otherwise="or none for the platform default")
    return problems


def given(values: Mapping[str, object]) -> list[int]:
    """The positions of the nodepools that give a ``scale_down_policy``."""
    return [i for i, pool in nodepool_entries(values, "nodepools") if chosen(pool) is not None]


def template_problems(values: Mapping[str, object], template: str) -> list[str]:
    """Each nodepool that gives a policy while ``template`` does not read the input.

    A cluster created from such a flavor would scale down at random, so it is
    not saved until the specs project's template reads the input, by the
    create form's own analysis of it (ADR-0063, ADR-0064). An empty template,
    or one that is not valid Jinja, is left to the create, which refuses both.
    """
    positions = given(values)
    if not positions or not template.strip():
        return []
    try:
        schema = analyze_template(template, include_reserved=True)
    except RenderError:
        return []
    pools = next((f for f in schema if f.name == "nodepools"), None)
    if pools is not None and any(f.name == INPUT for f in pools.fields):
        return []
    return [
        f"nodepools[{i}].{INPUT}: the specs project's cluster-template.j2 does not read this "
        "input, so a cluster created from this flavor would scale down at random; add the "
        f"template lines in {GUIDE} (ADR-0062)"
        for i in positions
    ]


def rendered_problems(inputs: Mapping[str, object], rendered: Mapping[str, object]) -> list[str]:
    """Each rendered nodepool whose policy annotation is not the one chosen, or is there unasked.

    The guard against a specs-project template that does not render the
    input: the NodePool would silently scale down at random.
    """
    asked = dict(nodepool_entries(inputs, "nodepools"))
    problems: list[str] = []
    for index, pool in nodepool_entries(rendered, "nodepool"):
        want = chosen(asked.get(index, {}))
        have = policy_of(pool)
        if have != want:
            problems.append(
                f"nodepool[{index}].{ANNOTATIONS}: the template wrote {SCALE_DOWN_POLICY} "
                f"{have!r} for {want!r}; the specs project's cluster-template.j2 must render "
                f"{INPUT} as given ({GUIDE})"
            )
    return problems


def lock_problem(path: str, values: Mapping[str, object]) -> str | None:
    """A locked ``nodepools[<i>].scale_down_policy`` must fix a policy: locking none fixes nothing.

    The other rules of its value are :func:`input_problems`'.
    """
    found = _LOCK.fullmatch(path)
    if found is None:
        return None
    pools = nodepool_entries(values, "nodepools")
    pool = dict(pools).get(int(found.group(1)), {})
    if chosen(pool) is not None:
        return None
    return (
        f"locked_paths: {path} is locked to no policy; lock one of {_KNOWN}, or leave it "
        "unlocked for the platform default"
    )


# ── Edits of an existing file ────────────────────────────────────────────────


def edit_problems(old: Mapping[str, object], new: Mapping[str, object]) -> list[str]:
    """Each nodepool an edit gives a policy the workflow does not know, or the chart's sync-wave.

    Only a policy the edit sets or changes: an unknown one the file already
    holds stays the workflow's to refuse, at its next scale-down. Nodepools
    are matched by ``name``, else ``infraEnvName``, else position, as the
    other edit rules match them. The chart writes the NodePool's
    ``argocd.argoproj.io/sync-wave`` itself, before the entry's annotations,
    so an entry that sets it would give the NodePool the key twice.
    """
    before = {_key(i, p): policy_of(p) for i, p in nodepool_entries(old, "nodepool")}
    problems: list[str] = []
    for index, pool in nodepool_entries(new, "nodepool"):
        annotations = pool.get(ANNOTATIONS)
        if isinstance(annotations, Mapping) and SYNC_WAVE in annotations:
            problems.append(
                f"nodepool[{index}].{ANNOTATIONS}: {SYNC_WAVE} is the hostedclusters-setup "
                "chart's own; remove it from the entry"
            )
        policy = policy_of(pool)
        if policy is None or policy == before.get(_key(index, pool)):
            continue
        where = f"nodepool[{index}].{ANNOTATIONS}.{SCALE_DOWN_POLICY}"
        problems += value_problems(where, policy, otherwise="or remove the annotation")
    return problems


def _key(index: int, pool: Mapping[str, object]) -> str:
    return str(pool.get("name") or pool.get("infraEnvName") or f"#{index}")
