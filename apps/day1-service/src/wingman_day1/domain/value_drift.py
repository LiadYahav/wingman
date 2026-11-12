"""Value drift: each locked value a cluster file does not hold (ADR-0036).

A flavor's locks are template inputs (``nodepools[0].configs``); the file
holds what the shared template wrote for them (``nodepool[0].configs``),
through the ``LOCKABLE`` table. This module compares the two, in the file's
own form:

- an owner compares as text (``"0042"``), a whole number in the file being
  the same as its digits;
- ``platform`` is ``kubevirt`` or the Agent default; a file without the key
  is on the Agent platform, as the template writes it;
- replicas compare as numbers, node labels as a mapping (no key is ``{}``);
- configs compare by name, each as often, in any order (ADR-0029); a lock's
  ``{name: nm-conf, hardware: <hw>}`` is the file's
  ``nm-conf-<clusterName>-<hw>``. Where the hardware is the nodepool's own
  (the configs rule, or a lock with no hardware), it is read from the one
  network config the nodepool lists; none or several needs a person.

Presets are never compared: overriding them is allowed. Each difference is
a :class:`ValueDrift` with the flavor's value and the file's, and for
configs the names a sync would add and remove.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from wingman_day1.domain.locks import (
    MISSING,
    NETWORK_ENTRY,
    InputPath,
    Lock,
    entry_key,
    is_configs_lock,
    lockable,
    lookup,
    same_value,
)
from wingman_day1.domain.machine_configs import MachineConfigCatalog, network_config_name

_KUBEVIRT: Final = "kubevirt"
_AGENT: Final = "agent"
_SHOWN: Final = 80


@dataclass(frozen=True, slots=True)
class NodepoolRef:
    """A nodepool of the file: its position and the NodePool name the chart renders."""

    index: int
    name: str


@dataclass(frozen=True, slots=True)
class ValueDrift:
    """One locked value the cluster file does not hold."""

    lock: InputPath
    """The flavor's locked path: ``owner_anaf``, ``nodepools[0].configs`` or the rule."""
    file_key: InputPath
    """Where the value is in the file: ``owner.anaf``, ``nodepool[1].configs``."""
    flavor_value: object
    """The locked value in the file's form; an undecided network config is ``{name: nm-conf}``."""
    cluster_value: object
    """What the file holds there; ``MISSING`` when it has no such key."""
    nodepool: NodepoolRef | None = None
    added: tuple[str, ...] = ()
    """Configs only: the names a sync adds."""
    removed: tuple[str, ...] = ()
    """Configs only: the names a sync removes (exact, ADR-0029)."""
    needs_decision: str | None = None
    """Why a sync cannot set this value until a person decides; ``None`` when it can."""
    needs_hardware: bool = False
    """The decision is the nodepool's network hardware type: a sync request can choose it."""

    @property
    def is_configs(self) -> bool:
        """Whether this is a nodepool's configs: changing them rolls the nodepool's nodes."""
        return self.file_key.segments[-1] == "configs"


def file_nodepools(values: Mapping[str, object]) -> list[object]:
    """The file's ``nodepool`` list; ``[]`` when it has none or it is not a list."""
    pools = values.get("nodepool")
    return list(cast("Sequence[object]", pools)) if isinstance(pools, list) else []


def nodepool_name(pool: object, index: int, *, cluster_name: str) -> str:
    """The NodePool the chart renders: ``name``, else ``<clusterName>-<infraEnvName>``."""
    if isinstance(pool, Mapping):
        found = cast("Mapping[str, object]", pool)
        if found.get("name"):
            return str(found["name"])
        if found.get("infraEnvName"):
            return f"{cluster_name}-{found['infraEnvName']}"
    return f"nodepool[{index}]"


def config_names(configs: object) -> list[str]:
    """The names a file's ``configs`` value lists, in order (``[]`` when it is not a list)."""
    if not isinstance(configs, list):
        return []
    return [entry_key(item) for item in cast("Sequence[object]", configs)]


def show_value(value: object) -> str:
    """A drifted value as an MR description shows it: configs by name, cut at 80 characters."""
    if value is MISSING:
        return "(absent)"
    if isinstance(value, list):
        names = [
            str(cast("Mapping[str, object]", e).get("name")) if isinstance(e, Mapping) else str(e)
            for e in cast("Sequence[object]", value)
        ]
        text = ", ".join(names) or "none"
    else:
        text = repr(value) if isinstance(value, str) else str(value)
    return text if len(text) <= _SHOWN else f"{text[: _SHOWN - 3]}..."


def compare_names(expected: Sequence[str], have: Sequence[str]) -> tuple[list[str], list[str]]:
    """What to add (in ``expected`` order) and remove (in file order) so ``have`` is ``expected``.

    Names compare as a multiset: order is ignored, and a name listed twice
    where ``expected`` has it once is removed once.
    """
    remaining = Counter(expected)
    removed: list[str] = []
    for name in have:
        if remaining[name] > 0:
            remaining[name] -= 1
        else:
            removed.append(name)
    added: list[str] = []
    for name in expected:
        if remaining[name] > 0:
            added.append(name)
            remaining[name] -= 1
    return added, removed


@dataclass(frozen=True, slots=True)
class _Context:
    values: Mapping[str, object]
    cluster_name: str
    catalog: MachineConfigCatalog
    hardware: Mapping[int, str]


def network_configs(names: Sequence[str], catalog: MachineConfigCatalog) -> list[str]:
    """The names a hardware template captures: the nodepool's network configs (ADR-0027)."""
    return [name for name in names if catalog.template_for(name) is not None]


def _network(index: int, have: Sequence[str], context: _Context) -> tuple[str | None, str | None]:
    """The nodepool's own network config name, or why a person must choose its hardware."""
    chosen = context.hardware.get(index)
    if chosen is not None:
        return network_config_name(context.cluster_name, chosen), None
    found = network_configs(have, context.catalog)
    template = context.catalog.template_for(found[0]) if len(found) == 1 else None
    if template is not None:
        return network_config_name(context.cluster_name, template.name), None
    pattern = network_config_name(context.cluster_name, "<hardware>")
    if not found:
        return None, (
            f"nodepool[{index}] has no network config ({pattern}); choose its hardware type"
        )
    return None, (
        f"nodepool[{index}] has {len(found)} network configs ({', '.join(found)}); choose the "
        "hardware type it keeps"
    )


def _configs_drift(
    lock: Lock, index: int, pool: Mapping[str, object], context: _Context
) -> ValueDrift | None:
    entries = cast("Sequence[object]", lock.value) if isinstance(lock.value, list) else []
    have_value = pool.get("configs", MISSING)
    have = config_names(have_value)
    expected: list[str] = []
    shown: list[dict[str, str]] = []
    decision: str | None = None
    network_names = set(network_configs(have, context.catalog))
    for entry in entries:
        name = entry_key(entry)
        hardware = (
            cast("Mapping[str, object]", entry).get("hardware")
            if isinstance(entry, Mapping)
            else None
        )
        if name != NETWORK_ENTRY:
            expected.append(name)
            shown.append({"name": name})
        elif isinstance(hardware, str) and hardware and not lock.is_rule:
            expanded = network_config_name(context.cluster_name, hardware)
            expected.append(expanded)
            shown.append({"name": expanded})
        else:
            expanded, decision = _network(index, have, context)
            if expanded is None:
                shown.append({"name": NETWORK_ENTRY})
            else:
                expected.append(expanded)
                shown.append({"name": expanded})
    if decision is not None:
        # The network part waits for a person; the rest is compared as usual.
        added, removed = compare_names(expected, [n for n in have if n not in network_names])
    else:
        added, removed = compare_names(expected, have)
    if not added and not removed and decision is None:
        return None
    file_key = InputPath(("nodepool", index, "configs"))
    return ValueDrift(
        lock=lock.path,
        file_key=file_key,
        flavor_value=shown,
        cluster_value=have_value,
        nodepool=NodepoolRef(index, nodepool_name(pool, index, cluster_name=context.cluster_name)),
        added=tuple(added),
        removed=tuple(removed),
        needs_decision=decision,
        needs_hardware=decision is not None,
    )


def _no_nodepool(lock: Lock, file_key: InputPath, index: int, why: str) -> ValueDrift:
    return ValueDrift(
        lock=lock.path,
        file_key=file_key,
        flavor_value=lock.value,
        cluster_value=MISSING,
        needs_decision=why.format(index=index),
    )


def _nodepool_drift(lock: Lock, file_key: InputPath, context: _Context) -> ValueDrift | None:
    index = cast("int", lock.path.segments[1])
    pools = file_nodepools(context.values)
    if index >= len(pools):
        return _no_nodepool(
            lock,
            file_key,
            index,
            "the cluster has no nodepool[{index}]; sync does not add nodepools",
        )
    pool = pools[index]
    if not isinstance(pool, Mapping):
        return _no_nodepool(lock, file_key, index, "nodepool[{index}] is not a mapping")
    found = cast("Mapping[str, object]", pool)
    if is_configs_lock(lock.path):
        return _configs_drift(lock, index, found, context)
    key = str(file_key.segments[-1])
    have = found.get(key, MISSING)
    ref = NodepoolRef(index, nodepool_name(found, index, cluster_name=context.cluster_name))
    want = lock.value
    if key == "replicas" and isinstance(want, str) and want.isdigit():
        want = int(want)
    if key == "nodeLabels" and have is MISSING and want == {}:
        return None  # the template writes no nodeLabels for an empty mapping
    if have is not MISSING and same_value(want, have):
        return None
    return ValueDrift(lock.path, file_key, want, have, nodepool=ref)


def _top_level_drift(lock: Lock, file_key: InputPath, context: _Context) -> ValueDrift | None:
    have = lookup(context.values, file_key)
    if file_key.segments == ("platform",):
        want = _KUBEVIRT if lock.value == _KUBEVIRT else _AGENT
        effective = _KUBEVIRT if have == _KUBEVIRT else _AGENT
        return None if want == effective else ValueDrift(lock.path, file_key, want, have)
    want = str(lock.value) if type(lock.value) is int else lock.value
    if have is not MISSING and same_value(want, have):
        return None
    return ValueDrift(lock.path, file_key, want, have)


def value_drift(
    locks: Sequence[Lock],
    values: Mapping[str, object],
    *,
    cluster_name: str,
    catalog: MachineConfigCatalog,
    hardware: Mapping[int, str] | None = None,
) -> tuple[ValueDrift, ...]:
    """Every locked value ``values`` (a parsed cluster file) does not hold, in lock order.

    ``cluster_name`` is the chart's (an explicit ``clusterName`` key wins);
    ``hardware`` is a person's choice of network hardware per nodepool
    index, for nodepools whose own cannot be read.
    """
    context = _Context(values, cluster_name, catalog, hardware or {})
    found: list[ValueDrift] = []
    for lock in locks:
        if lock.is_rule:
            for index, pool in enumerate(file_nodepools(values)):
                if not isinstance(pool, Mapping):
                    found.append(
                        _no_nodepool(
                            lock,
                            InputPath(("nodepool", index, "configs")),
                            index,
                            "nodepool[{index}] is not a mapping",
                        )
                    )
                    continue
                drift = _configs_drift(lock, index, cast("Mapping[str, object]", pool), context)
                if drift is not None:
                    found.append(drift)
            continue
        shape = lockable(lock.path)
        if shape is None:
            continue
        file_key = shape.file_path(lock.path)
        if file_key.segments[0] == "nodepool":
            drift = _nodepool_drift(lock, file_key, context)
        else:
            drift = _top_level_drift(lock, file_key, context)
        if drift is not None:
            found.append(drift)
    return tuple(found)
