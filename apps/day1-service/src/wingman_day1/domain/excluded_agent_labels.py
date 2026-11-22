"""Agent labels every NodePool excludes: an operator's default, one cluster at a time (ADR-0065).

herzi collects used Agents: it labels every Agent installed in a cluster
("used, delete when free"), because an uninstall or a scale-down does not
return a used Agent to the inventory cleanly, and deletes an Agent it finds
free with that label. Between the two, a freed used Agent must never be bound
again, so every NodePool's ``agentLabelSelector`` excludes the label
(``{key: <label>, operator: DoesNotExist}``). The label's name is herzi's to
choose, so Wingman keeps a list of keys, not one name.

Where the list lives: ``DAY1_EXCLUDED_AGENT_LABELS`` (comma-separated Agent
label keys, empty by default) → the template input ``excluded_agent_labels``,
which Wingman sets itself (nobody picks it on the create form) → each agent
nodepool entry's ``excludeAgentLabels: [..]`` in the cluster file → the
hostedclusters-setup chart, whose NodePool selector then gains
``matchExpressions``: the InfraEnvs' ``In`` requirement, then a
``DoesNotExist`` per key (beside ``matchLabels`` for one InfraEnv). Written
into each cluster file rather than as a chart-wide list, a change reaches a
cluster only through that cluster's own merge request: a small blast radius,
and every NodePool's selector is in Git where its cluster is. A KubeVirt
NodePool takes no Agents and gets none (Wingman's rule; the chart does not
check).

Existing clusters get it only through their own merge requests: an edit, or
the explicit per-cluster one (:func:`plan`). Never all at once. On an
``upgradeType: Replace`` NodePool a changed selector replaces every node, so
an edit that changes an existing Replace NodePool's list is refused; a new
NodePool, and an ``InPlace`` one (the chart's default), take it with no node
touched: the selector is read only when a new Machine claims an Agent.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from wingman_day1.domain.nodepool_infra_envs import REPLACE, nodepool_entries

FILE_KEY: Final = "excludeAgentLabels"
"""A ``nodepool[]`` entry's Agent label keys its NodePool excludes."""
INPUT: Final = "excluded_agent_labels"
"""The template input Wingman sets from the setting, the same for every nodepool."""
SETTING: Final = "DAY1_EXCLUDED_AGENT_LABELS"
GUIDE: Final = "docs/upgrade/3.48-to-3.49.md"
MAX_LABELS: Final = 16
_KUBEVIRT: Final = "kubevirt"
_NAME = re.compile(r"[A-Za-z0-9]([-A-Za-z0-9_.]{0,61}[A-Za-z0-9])?")
_PREFIX = re.compile(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*")


def label_key_problems(key: str) -> list[str]:
    """Why ``key`` is not a Kubernetes label key (``[prefix/]name``); empty when it is."""
    prefix, _, name = key.rpartition("/")
    problems: list[str] = []
    if not _NAME.fullmatch(name):
        problems.append(
            f"{key!r}: the name part must be 1 to 63 letters, digits, '-', '_' or '.', and "
            "start and end with a letter or digit"
        )
    if "/" in key and (len(prefix) > 253 or not _PREFIX.fullmatch(prefix)):
        problems.append(f"{key!r}: the prefix must be a DNS subdomain, such as redbull.io")
    return problems


def parse(text: str) -> tuple[str, ...]:
    """The setting's keys: split on commas, trimmed, empty ones dropped, each once."""
    return tuple(dict.fromkeys(part.strip() for part in text.split(",") if part.strip()))


def setting_problems(keys: Sequence[str]) -> list[str]:
    """Why the setting's keys cannot be used; empty when they can."""
    problems = [p for key in keys for p in label_key_problems(key)]
    if len(keys) > MAX_LABELS:
        problems.append(f"{len(keys)} keys; the limit is {MAX_LABELS}")
    return problems


def labels_for(platform: object, labels: Sequence[str]) -> list[str]:
    """What a create's nodepools exclude: the setting's keys; none on KubeVirt (no Agents)."""
    return [] if platform == _KUBEVIRT else list(labels)


def keys_of(entry: Mapping[str, object]) -> list[str] | None:
    """A file entry's ``excludeAgentLabels`` (none: ``[]``); ``None`` when not a list of text."""
    value = entry.get(FILE_KEY)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return None
    return cast("list[str]", value)


# ── A create ────────────────────────────────────────────────────────────────


_SET_BY_DEPLOYMENT: Final = (
    f"{INPUT}: set by this deployment ({SETTING}) for every cluster, not per cluster or per "
    "flavor; leave it out"
)


def input_problems(inputs: Mapping[str, object], labels: Sequence[str]) -> list[str]:
    """A create that sends the input: refused unless it is exactly what the deployment sets."""
    sent = inputs.get(INPUT)
    want = labels_for(inputs.get("platform"), labels)
    return [] if sent is None or sent == want else [_SET_BY_DEPLOYMENT]


def flavor_problems(values: Mapping[str, object]) -> list[str]:
    """A flavor never gives the input: it is the deployment's, the same for every cluster."""
    return [_SET_BY_DEPLOYMENT] if INPUT in values else []


def with_labels(inputs: Mapping[str, object], labels: Sequence[str]) -> dict[str, object]:
    """``inputs`` with :data:`INPUT` set as the deployment does (none on KubeVirt)."""
    return {**inputs, INPUT: labels_for(inputs.get("platform"), labels)}


def rendered_problems(inputs: Mapping[str, object], rendered: Mapping[str, object]) -> list[str]:
    """Each rendered nodepool whose ``excludeAgentLabels`` is not the setting's, or is unasked.

    The guard against a specs-project template that does not render the input:
    the NodePools would bind used Agents herzi is about to delete.
    """
    want = cast("list[str]", inputs.get(INPUT) or [])
    problems: list[str] = []
    for index, pool in nodepool_entries(rendered, "nodepool"):
        have = pool.get(FILE_KEY)
        if (have or []) != want or (FILE_KEY in pool and not want):
            problems.append(
                f"nodepool[{index}].{FILE_KEY}: the template wrote {have!r} for {want}; the specs "
                f"project's cluster-template.j2 must render {INPUT} on every nodepool ({GUIDE})"
            )
    return problems


# ── Edits of an existing file ────────────────────────────────────────────────


def _key(index: int, pool: Mapping[str, object]) -> str:
    return str(pool.get("name") or pool.get("infraEnvName") or f"#{index}")


def edit_problems(old: Mapping[str, object], new: Mapping[str, object]) -> list[str]:
    """Why an edit's ``excludeAgentLabels`` may not be proposed; empty when it may.

    A changed list must be Agent label keys; and an existing ``Replace``
    NodePool's list may not change: its selector change would replace every
    node. Nodepools are matched by ``name``, else ``infraEnvName``.
    """
    before = {_key(i, p): p for i, p in nodepool_entries(old, "nodepool")}
    problems: list[str] = []
    for index, pool in nodepool_entries(new, "nodepool"):
        was = before.get(_key(index, pool))
        keys = keys_of(pool)
        if keys == (keys_of(was) if was is not None else []):
            continue
        where = f"nodepool[{index}].{FILE_KEY}"
        if keys is None:
            problems.append(f"{where}: must be a list of Agent label keys")
            continue
        problems += [f"{where}: {p}" for key in keys for p in label_key_problems(key)]
        if was is not None and REPLACE in (pool.get("upgradeType"), was.get("upgradeType")):
            problems.append(
                f"{where}: NodePool {_key(index, pool)} is upgradeType Replace, so a change of "
                "the Agents it excludes would replace every node; leave it as it is, or change "
                "the NodePool to InPlace first"
            )
    return problems


# ── The per-cluster merge request ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PoolPlan:
    """One nodepool of the file: what it excludes now, and what the merge request does to it."""

    index: int
    name: str
    """Its NodePool's: the entry's ``name``, else ``<clusterName>-<infraEnvName>``."""
    have: tuple[str, ...]
    """Its ``excludeAgentLabels`` as written (none: empty)."""
    change: bool
    """Whether the merge request writes the setting's keys on it."""
    reason: str
    """Why it changes, or why not."""


def _nodepool_name(index: int, pool: Mapping[str, object], cluster_name: str) -> str:
    """The NodePool the chart renders: ``value_drift.nodepool_name``'s rule (an import cycle)."""
    if pool.get("name"):
        return str(pool["name"])
    if pool.get("infraEnvName"):
        return f"{cluster_name}-{pool['infraEnvName']}"
    return f"nodepool[{index}]"


def plan(
    values: Mapping[str, object], labels: Sequence[str], *, cluster_name: str
) -> tuple[PoolPlan, ...]:
    """Each nodepool and whether the per-cluster merge request writes the setting's keys on it.

    A nodepool that already excludes exactly them is left; a KubeVirt
    cluster's take no Agents; a Replace NodePool would have every node
    replaced, so it is left and says so; every other gets the keys. Each is
    named by its NodePool, the name the MCE shows (``cluster_name`` is the
    chart's ``clusterName``).
    """
    kubevirt = values.get("platform") == _KUBEVIRT
    found: list[PoolPlan] = []
    for index, pool in nodepool_entries(values, "nodepool"):
        have = tuple(keys_of(pool) or ())
        name = _nodepool_name(index, pool, cluster_name)
        if kubevirt:
            found.append(PoolPlan(index, name, have, False, "KubeVirt: takes no Agents"))
        elif list(have) == list(labels):
            found.append(PoolPlan(index, name, have, False, "excludes them already"))
        elif pool.get("upgradeType") == REPLACE:
            reason = "upgradeType Replace: the change would replace every node"
            found.append(PoolPlan(index, name, have, False, reason))
        else:
            found.append(
                PoolPlan(index, name, have, True, "the selector is read for new nodes only")
            )
    return tuple(found)


def summary(cluster: str, labels: Sequence[str], pools: Sequence[PoolPlan]) -> str:
    """The merge request's own text: the NodePools it changes, then each it leaves out, and why."""
    changed = ", ".join(p.name for p in pools if p.change)
    text = (
        f"Exclude Agents labelled {', '.join(labels)} from NodePools {changed} of **{cluster}** "
        "(ADR-0065). An InPlace NodePool's running nodes are untouched: the selector is read "
        "only when a new node claims an Agent."
    )
    left = [f"- {p.name} ({p.reason})" for p in pools if not p.change]
    return "\n".join([text, "", "Left out:", *left]) if left else text
