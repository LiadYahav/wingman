"""The tuning rule and the rendered tuning names (ADR-0061).

``nodepools[*].tuning_config`` locks every nodepool's tuning profiles, as
``nodepools[*].configs`` locks its configs (ADR-0029), but compared as a
set: order and repetition change nothing on the nodes. Its value is the
names every flavor nodepool sets, which must agree and may not be empty.
Before a render each nodepool's names take the file's form (a string for
one, a list for several), and after it the file must hold exactly them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import cast

from wingman_day1.domain.nodepool_infra_envs import nodepool_entries
from wingman_day1.domain.tuning_profiles import (
    TUNING_FILE_KEY,
    TUNING_INPUT,
    file_value,
    show_names,
    tuning_names,
)

# ── Rendering ────────────────────────────────────────────────────────────────


def render_inputs(inputs: Mapping[str, object]) -> dict[str, object]:
    """``inputs`` with each nodepool's ``tuning_config`` in the file's form.

    One name becomes a string, several stay a list, none drops the key, so
    the shared template writes ``tuningConfig`` as the user decided. A value
    of another shape is left for the input checks to refuse.
    """
    pools = inputs.get("nodepools")
    if not isinstance(pools, (list, tuple)):
        return dict(inputs)
    result: list[object] = []
    for pool in cast("Sequence[object]", pools):
        if not isinstance(pool, Mapping) or TUNING_INPUT not in pool:
            result.append(pool)
            continue
        found = dict(cast("Mapping[str, object]", pool))
        names = tuning_names(found[TUNING_INPUT])
        if names == []:
            del found[TUNING_INPUT]
        elif names is not None:
            found[TUNING_INPUT] = file_value(names)
        result.append(found)
    return {**inputs, "nodepools": result}


def rendered_problems(inputs: Mapping[str, object], rendered: Mapping[str, object]) -> list[str]:
    """Each nodepool whose rendered ``tuningConfig`` is not the names it chose."""
    chosen = dict(nodepool_entries(inputs, "nodepools"))
    problems: list[str] = []
    for index, pool in nodepool_entries(rendered, "nodepool"):
        want = tuning_names(chosen.get(index, {}).get(TUNING_INPUT)) or []
        have = tuning_names(pool.get(TUNING_FILE_KEY))
        if have != want:
            problems.append(
                f"nodepool[{index}].{TUNING_FILE_KEY}: the template wrote "
                f"{pool.get(TUNING_FILE_KEY)!r} for {show_names(want)}; the specs project's "
                "cluster-template.j2 must render tuning_config as given (ADR-0061)"
            )
    return problems


# ── The tuning rule ──────────────────────────────────────────────────────────


def rule_value(values: Mapping[str, object], rule: str) -> list[str] | str:
    """The names every flavor nodepool sets for the tuning rule, or why it has none.

    Every nodepool must set at least one name, and all the same ones (as a
    set); the value is the first nodepool's, in its order.
    """
    pools = values.get("nodepools")
    if not isinstance(pools, (list, tuple)) or not pools:
        return f"locked_paths: {rule} is locked but spec.day1.values sets no nodepools for it"
    lists: list[list[str]] = []
    for index, pool in enumerate(cast("Sequence[object]", pools)):
        raw = (
            cast("Mapping[str, object]", pool).get(TUNING_INPUT)
            if isinstance(pool, Mapping)
            else None
        )
        names = tuning_names(raw)
        if not names:
            return (
                f"locked_paths: {rule} locks every nodepool's tuning profiles, but "
                f"spec.day1.values.nodepools[{index}] sets none"
            )
        lists.append(names)
    for index, other in enumerate(lists[1:], start=1):
        if set(other) != set(lists[0]):
            return (
                f"locked_paths: {rule} locks every nodepool to the same tuning profiles, but "
                f"nodepools[{index}].{TUNING_INPUT} names other profiles than "
                f"nodepools[0].{TUNING_INPUT}"
            )
    return list(dict.fromkeys(lists[0]))


def rule_conflicts(
    variables: Mapping[str, object], names: Sequence[str], *, flavor: str
) -> list[str]:
    """Each nodepool a create sends other tuning profiles for than the rule's."""
    problems: list[str] = []
    for index, pool in nodepool_entries(variables, "nodepools"):
        if TUNING_INPUT not in pool:
            continue
        sent = tuning_names(pool[TUNING_INPUT])
        if sent is None or set(sent) != set(names):
            problems.append(
                f"nodepools[{index}].{TUNING_INPUT}: locked by flavor {flavor}: every nodepool "
                f"has {show_names(names)}, in any order; the request sends "
                f"{show_names(sent) if sent is not None else repr(pool[TUNING_INPUT])}"
            )
    return problems


def rule_fill(inputs: Mapping[str, object], names: Sequence[str]) -> dict[str, object]:
    """``inputs`` with the rule's names on every nodepool that sends none."""
    pools = inputs.get("nodepools")
    if not isinstance(pools, (list, tuple)):
        return dict(inputs)
    return {
        **inputs,
        "nodepools": [
            {**cast("Mapping[str, object]", pool), TUNING_INPUT: list(names)}
            if isinstance(pool, Mapping) and TUNING_INPUT not in pool
            else pool
            for pool in cast("Sequence[object]", pools)
        ],
    }


def compare(want: Iterable[str], have: Sequence[str]) -> tuple[list[str], list[str]]:
    """What to add (in ``want`` order) and remove (in ``have`` order), as sets."""
    wanted = list(dict.fromkeys(want))
    return [n for n in wanted if n not in have], [n for n in dict.fromkeys(have) if n not in wanted]
