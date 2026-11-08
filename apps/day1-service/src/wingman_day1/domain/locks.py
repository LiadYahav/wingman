"""Flavor locks: a value the flavor fixes and every create must use (ADR-0026, ADR-0029).

A flavor's ``spec.day1.values`` holds template inputs. Each one is a
**preset** (prefilled at create; the person creating the cluster may change
it) or **locked**: its path is in ``spec.day1.locked_paths``, the flavor's
value is what the cluster gets, a create that sends another value for that
path is refused, and a cluster file that holds another value has drifted.

Paths
=====

A path names one template input the way the create form addresses it::

    path  := name ( "." name | "[" index "]" )*
    name  := [A-Za-z_][A-Za-z0-9_]*       an identifier, as every input name is
    index := "0" | [1-9][0-9]{0,2} | "*"  a list position (no leading zero, below 1000),
                                          or every position

at most 253 characters, with no spaces: ``owner_merkaz``,
``nodepools[0].configs``, ``nodepools[*].configs``. :class:`InputPath`
parses and prints it; cluster file keys (``nodepool[0].nodeLabels``) are
written the same way.

What can be locked
==================

Only what day1 drift can compare with the cluster file. Each lockable input
and the file key the shared template writes it to:

==============================  ============================
template input                  cluster-file key
==============================  ============================
``owner_merkaz``                ``owner.merkaz``
``owner_anaf``                  ``owner.anaf``
``owner_mador``                 ``owner.mador``
``platform``                    ``platform``
``nodepools[<i>].replicas``     ``nodepool[<i>].replicas``
``nodepools[<i>].configs``      ``nodepool[<i>].configs``
``nodepools[<i>].node_labels``  ``nodepool[<i>].nodeLabels``
``nodepools[*].configs``        ``nodepool[*].configs``
==============================  ============================

A value can differ in form between the two sides: a ``{name: nm-conf,
hardware: <hw>}`` entry is ``{name: nm-conf-<clusterName>-<hw>}`` in the
file (``machine_configs.expand_network_configs``), and ``platform`` is
written only as ``platform: kubevirt``. The inputs Wingman sets for each
cluster (name, site, MCE, OpenShift version) are never lockable.

The configs rule
================

A position (``nodepools[0]``) means something only for a cluster the flavor
creates: an existing cluster's nodepools come in any number and order.
``nodepools[*].configs`` is a **rule**: every nodepool of the cluster has
exactly these configs, compared by name and in any order, and ``nm-conf`` is
each nodepool's own network config for its own hardware type. Its value is
the configs every nodepool in ``spec.day1.values.nodepools`` sets, which must
agree (the hardware of their ``nm-conf`` entries stays a per-nodepool preset
for create), and it must list ``nm-conf`` once: a rule that left it out would
remove every nodepool's network config.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from wingman_day1.domain.template import LEGACY_IDENTITY_ALIASES, RESERVED_INPUTS

MAX_PATH_LENGTH: Final = 253
MAX_LOCKS: Final = 100
NETWORK_ENTRY: Final = "nm-conf"
"""The config entry that stands for a nodepool's own network config (ADR-0027)."""

_HEAD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STEP = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(0|[1-9][0-9]{0,2}|\*)\]")


class _Every:
    """The ``[*]`` of a rule: every position of a list."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "EVERY"


EVERY: Final = _Every()
"""The segment ``[*]`` parses to."""

Segment = str | int | _Every


class InvalidPathError(ValueError):
    """A string that is not a template-input path."""


@dataclass(frozen=True, slots=True)
class InputPath:
    """A path to one template input (or one cluster-file key): names and list positions."""

    segments: tuple[Segment, ...]

    @classmethod
    def parse(cls, text: str) -> InputPath:
        """``nodepools[0].configs`` → ``("nodepools", 0, "configs")``; ``[*]`` is ``EVERY``.

        Raises ``InvalidPathError`` with the reason.
        """
        if len(text) > MAX_PATH_LENGTH:
            raise InvalidPathError(f"longer than {MAX_PATH_LENGTH} characters")
        head = _HEAD.match(text)
        if head is None:
            raise InvalidPathError("must start with an input name")
        segments: list[Segment] = [head.group()]
        position = head.end()
        while position < len(text):
            step = _STEP.match(text, position)
            if step is None:
                raise InvalidPathError(f"unexpected {text[position]!r} at character {position + 1}")
            name, index = step.groups()
            if name is not None:
                segments.append(name)
            else:
                segments.append(EVERY if index == "*" else int(index))
            position = step.end()
        return cls(tuple(segments))

    def __str__(self) -> str:
        """The path as written: ``nodepools[0].configs``, ``nodepools[*].configs``."""
        out = ""
        for segment in self.segments:
            if segment is EVERY:
                out += "[*]"
            elif isinstance(segment, int):
                out += f"[{segment}]"
            else:
                out += f".{segment}" if out else str(segment)
        return out

    @property
    def parent(self) -> InputPath:
        """The path without its last segment."""
        return InputPath(self.segments[:-1])

    @property
    def is_rule(self) -> bool:
        """Whether the path has a ``[*]``: it names every position, not one."""
        return any(segment is EVERY for segment in self.segments)


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


MISSING: Final = _Missing()
"""What :func:`lookup` returns for a path that leads nowhere."""


def lookup(root: Mapping[str, object], path: InputPath) -> object:
    """The value at ``path``, or ``MISSING`` (always for a rule: it has no single value)."""
    current: object = root
    for segment in path.segments:
        if segment is EVERY:
            return MISSING
        if isinstance(segment, int):
            if not isinstance(current, (list, tuple)):
                return MISSING
            items = cast("Sequence[object]", current)
            if segment >= len(items):
                return MISSING
            current = items[segment]
        else:
            if not isinstance(current, Mapping):
                return MISSING
            mapping = cast("Mapping[str, object]", current)
            key = str(segment)
            if key not in mapping:
                return MISSING
            current = mapping[key]
    return current


def assigned(
    root: Mapping[str, object], path: InputPath, value: object
) -> dict[str, object] | None:
    """A copy of ``root`` with ``value`` at ``path``; ``None`` when the path's parent is missing.

    Only the containers along the path are copied; ``root`` is not changed. A
    rule path is never assigned this way.
    """

    def put(node: object, segments: tuple[Segment, ...]) -> object:
        segment, rest = segments[0], segments[1:]
        if segment is EVERY:
            return MISSING
        if isinstance(segment, int):
            if not isinstance(node, (list, tuple)):
                return MISSING
            items = list(cast("Sequence[object]", node))
            if segment >= len(items):
                return MISSING
            child = put(items[segment], rest) if rest else value
            if child is MISSING:
                return MISSING
            items[segment] = child
            return items
        if not isinstance(node, Mapping):
            return MISSING
        mapping = dict(cast("Mapping[str, object]", node))
        key = str(segment)
        if rest and key not in mapping:
            return MISSING
        child = put(mapping[key], rest) if rest else value
        if child is MISSING:
            return MISSING
        mapping[key] = child
        return mapping

    result = put(root, path.segments)
    return None if result is MISSING else cast("dict[str, object]", result)


# ── The lockable inputs and their cluster-file keys ──────────────────────────

_ANY_INDEX: Final = None

ShapeSegment = str | _Every | None


@dataclass(frozen=True, slots=True)
class Lockable:
    """One lockable input shape and the file key it is written to.

    ``None`` is any one position (``[<i>]``); ``EVERY`` is the rule's ``[*]``.
    """

    input: tuple[ShapeSegment, ...]
    file_key: tuple[ShapeSegment, ...]

    def matches(self, path: InputPath) -> bool:
        """Whether ``path`` has this shape."""
        return len(path.segments) == len(self.input) and all(
            _segment_matches(s, want) for s, want in zip(path.segments, self.input, strict=True)
        )

    def file_path(self, path: InputPath) -> InputPath:
        """The file key for ``path`` (which must match), with its positions."""
        positions = iter(s for s in path.segments if s is EVERY or isinstance(s, int))
        return InputPath(
            tuple(next(positions) if k is _ANY_INDEX or k is EVERY else k for k in self.file_key)
        )

    def __str__(self) -> str:
        """The shape as the docs write it: ``nodepools[<i>].configs``, ``nodepools[*].configs``."""
        out = ""
        for k in self.input:
            if k is _ANY_INDEX:
                out += "[<i>]"
            elif k is EVERY:
                out += "[*]"
            else:
                out += f".{k}" if out else str(k)
        return out


def _segment_matches(segment: Segment, want: ShapeSegment) -> bool:
    if want is _ANY_INDEX:
        return isinstance(segment, int)
    if want is EVERY:
        return segment is EVERY
    return segment == want


CONFIGS_RULE: Final = InputPath(("nodepools", EVERY, "configs"))
"""``nodepools[*].configs``: every nodepool has exactly these configs (ADR-0029)."""

LOCKABLE: Final = (
    Lockable(("owner_merkaz",), ("owner", "merkaz")),
    Lockable(("owner_anaf",), ("owner", "anaf")),
    Lockable(("owner_mador",), ("owner", "mador")),
    Lockable(("platform",), ("platform",)),
    Lockable(("nodepools", _ANY_INDEX, "replicas"), ("nodepool", _ANY_INDEX, "replicas")),
    Lockable(("nodepools", _ANY_INDEX, "configs"), ("nodepool", _ANY_INDEX, "configs")),
    Lockable(("nodepools", _ANY_INDEX, "node_labels"), ("nodepool", _ANY_INDEX, "nodeLabels")),
    Lockable(("nodepools", EVERY, "configs"), ("nodepool", EVERY, "configs")),
)
"""Every input a flavor can lock, with the cluster-file key the shared template writes."""

_PER_CLUSTER: Final = RESERVED_INPUTS | LEGACY_IDENTITY_ALIASES


def lockable(path: InputPath) -> Lockable | None:
    """The lockable shape ``path`` has, if any."""
    return next((shape for shape in LOCKABLE if shape.matches(path)), None)


def cluster_file_key(path: InputPath) -> InputPath | None:
    """The cluster-file key a lockable input is written to; ``None`` for any other input."""
    shape = lockable(path)
    return shape.file_path(path) if shape is not None else None


def is_configs_lock(path: InputPath) -> bool:
    """Whether ``path`` locks a nodepool's configs: by position or by the rule."""
    return (
        len(path.segments) == 3
        and path.segments[0] == "nodepools"
        and (path.segments[2] == "configs")
    )


# ── Config entries compared by name ──────────────────────────────────────────


def entry_key(entry: object) -> str:
    """How a rule compares one config entry: its name (``nm-conf`` whatever its hardware).

    An entry that is not ``{name: ...}`` compares as its JSON text, so it
    never equals a real entry.
    """
    if isinstance(entry, Mapping):
        name = cast("Mapping[str, object]", entry).get("name")
        if isinstance(name, str) and name:
            return name
    return json.dumps(entry, sort_keys=True, default=str)


def rule_entries(entries: Sequence[object]) -> list[dict[str, str]]:
    """The rule form of a config list: ``{name: ...}`` only, ``nm-conf`` without hardware."""
    return [{"name": entry_key(entry)} for entry in entries]


def same_configs(a: Sequence[object], b: Sequence[object]) -> bool:
    """Two config lists name the same configs, each as often, in any order."""
    return Counter(entry_key(e) for e in a) == Counter(entry_key(e) for e in b)


# ── Locks at flavor save and at create ───────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Lock:
    """A locked path and the value the flavor fixes it to.

    For the configs rule the value is the rule's entries, ``{name: ...}``
    each, with ``nm-conf`` standing for each nodepool's own network config.
    """

    path: InputPath
    value: object

    @property
    def is_rule(self) -> bool:
        """Whether this lock is the configs rule rather than one position."""
        return self.path.is_rule


_SHOWN: Final = 120


def _show(value: object) -> str:
    text = json.dumps(value, default=str, ensure_ascii=False)
    return text if len(text) <= _SHOWN else f"{text[: _SHOWN - 3]}..."


def _shape_problem(path: InputPath) -> str | None:
    if path.segments[0] in _PER_CLUSTER:
        return (
            f"locked_paths: {path} is set for each cluster at create (its name, site, MCE and "
            "OpenShift version) and cannot be locked"
        )
    if lockable(path) is None:
        shapes = ", ".join(str(s) for s in LOCKABLE)
        return f"locked_paths: {path} cannot be locked; lockable inputs are {shapes}"
    return None


def _parse(text: str) -> InputPath | str:
    """The path, or why ``text`` is not one."""
    try:
        return InputPath.parse(text)
    except InvalidPathError as exc:
        return (
            f"locked_paths: {text!r} is not a template-input path like owner_merkaz or "
            f"nodepools[0].configs ({exc})"
        )


def _rule_value(values: Mapping[str, object]) -> list[dict[str, str]] | str:
    """The configs rule's value from the flavor's nodepools, or why it has none."""
    pools = values.get("nodepools")
    if not isinstance(pools, (list, tuple)) or not pools:
        return (
            f"locked_paths: {CONFIGS_RULE} is locked but spec.day1.values sets no "
            "nodepools[0].configs for it"
        )
    lists: list[Sequence[object]] = []
    for index, pool in enumerate(cast("Sequence[object]", pools)):
        configs = (
            cast("Mapping[str, object]", pool).get("configs") if isinstance(pool, Mapping) else None
        )
        if not isinstance(configs, (list, tuple)):
            return (
                f"locked_paths: {CONFIGS_RULE} locks every nodepool's configs, but "
                f"spec.day1.values.nodepools[{index}] sets none"
            )
        lists.append(cast("Sequence[object]", configs))
    first = lists[0]
    for index, other in enumerate(lists[1:], start=1):
        if not same_configs(first, other):
            return (
                f"locked_paths: {CONFIGS_RULE} locks every nodepool to the same configs, but "
                f"nodepools[{index}].configs names other configs than nodepools[0].configs"
            )
    entries = rule_entries(first)
    if [e["name"] for e in entries].count(NETWORK_ENTRY) != 1:
        return (
            f"locked_paths: {CONFIGS_RULE} must list {NETWORK_ENTRY} exactly once: every "
            "nodepool needs its own network config, for its own hardware type"
        )
    return entries


def lock_problems(locked_paths: Sequence[str], values: Mapping[str, object]) -> list[str]:
    """Why ``locked_paths`` cannot be saved with ``values``; empty when they can.

    Each path must parse, be lockable, appear once, and have a value in
    ``values`` (a lock is a value the flavor fixes, so a lock without one
    fixes nothing). The configs rule needs agreeing nodepools that list
    ``nm-conf``, and no position may lock configs beside it.
    """
    problems: list[str] = []
    if len(locked_paths) > MAX_LOCKS:
        problems.append(f"locked_paths: {len(locked_paths)} paths; the limit is {MAX_LOCKS}")
    seen: set[InputPath] = set()
    for text in locked_paths:
        path = _parse(text)
        if isinstance(path, str):
            problems.append(path)
            continue
        problem = _shape_problem(path)
        if problem is not None:
            problems.append(problem)
            continue
        if path in seen:
            problems.append(f"locked_paths: {path} is listed twice")
            continue
        seen.add(path)
        if path.is_rule:
            rule = _rule_value(values)
            if isinstance(rule, str):
                problems.append(rule)
        elif lookup(values, path) is MISSING:
            problems.append(
                f"locked_paths: {path} is locked but spec.day1.values sets no value for it"
            )
    if CONFIGS_RULE in seen:
        problems += [
            f"locked_paths: {path} is covered by {CONFIGS_RULE}, which locks every nodepool's "
            "configs; lock one or the other"
            for path in sorted(seen, key=str)
            if not path.is_rule and is_configs_lock(path)
        ]
    return problems


def enforced_locks(locked_paths: Sequence[str], values: Mapping[str, object]) -> tuple[Lock, ...]:
    """The locks a create enforces: each lockable path once, with its value in ``values``.

    A spec saved before locks were enforced may list paths that break the
    save rules (:func:`lock_problems` reports them); those are not enforced.
    When the configs rule is enforced, no position's configs lock is: the
    rule already covers every nodepool.
    """
    locks: dict[InputPath, Lock] = {}
    for text in locked_paths:
        path = _parse(text)
        if isinstance(path, str) or _shape_problem(path) is not None:
            continue
        if path.is_rule:
            rule = _rule_value(values)
            if not isinstance(rule, str):
                locks[path] = Lock(path, rule)
            continue
        value = lookup(values, path)
        if value is not MISSING:
            locks[path] = Lock(path, value)
    if CONFIGS_RULE in locks:
        locks = {p: lock for p, lock in locks.items() if p.is_rule or not is_configs_lock(p)}
    return tuple(locks.values())


def same_value(a: object, b: object) -> bool:
    """JSON equality, plus: a whole number and the string of its digits are the same value.

    The template writes ``3`` and ``"3"`` the same way, and the create form
    sends numbers it edits as text. ``True`` is not ``1``.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, int) and isinstance(b, str):
        return str(a) == b
    if isinstance(a, str) and isinstance(b, int):
        return a == str(b)
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        left, right = cast("Mapping[object, object]", a), cast("Mapping[object, object]", b)
        return left.keys() == right.keys() and all(same_value(left[k], right[k]) for k in left)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        left_items, right_items = cast("Sequence[object]", a), cast("Sequence[object]", b)
        return len(left_items) == len(right_items) and all(
            same_value(x, y) for x, y in zip(left_items, right_items, strict=True)
        )
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def _pools(inputs: Mapping[str, object]) -> list[tuple[int, Mapping[str, object]]]:
    pools = inputs.get("nodepools")
    if not isinstance(pools, (list, tuple)):
        return []
    return [
        (index, cast("Mapping[str, object]", pool))
        for index, pool in enumerate(cast("Sequence[object]", pools))
        if isinstance(pool, Mapping)
    ]


def lock_conflicts(
    variables: Mapping[str, object], locks: Sequence[Lock], *, flavor: str
) -> list[str]:
    """Each locked path a create sends a different value for."""
    problems: list[str] = []
    for lock in locks:
        if lock.is_rule:
            rule = cast("Sequence[object]", lock.value)
            for index, pool in _pools(variables):
                sent = pool.get("configs")
                if isinstance(sent, (list, tuple)) and not same_configs(
                    rule, cast("Sequence[object]", sent)
                ):
                    problems.append(
                        f"nodepools[{index}].configs: locked by flavor {flavor}: every nodepool "
                        f"has {_show(lock.value)} ({NETWORK_ENTRY} for the nodepool's own "
                        f"hardware), in any order; the request sends {_show(sent)}"
                    )
            continue
        sent = lookup(variables, lock.path)
        if sent is not MISSING and not same_value(sent, lock.value):
            problems.append(
                f"{lock.path}: locked by flavor {flavor} to {_show(lock.value)}; the request "
                f"sends {_show(sent)}"
            )
    return problems


def apply_locks(
    inputs: Mapping[str, object], locks: Sequence[Lock]
) -> tuple[dict[str, object], list[str]]:
    """``inputs`` with every locked value in place, and each lock whose place does not exist.

    A request may leave a locked path out, or replace the list it sits in
    (lists are not merged), so the flavor's value is put back here. A lock
    on ``nodepools[2].replicas`` needs a third nodepool to exist. The configs
    rule fills every nodepool that sends no configs with the rule's entries;
    their ``nm-conf`` has no hardware yet, so the config check asks for one.
    """
    result = dict(inputs)
    problems: list[str] = []
    for lock in locks:
        if lock.is_rule:
            rule = cast("Sequence[Mapping[str, str]]", lock.value)
            pools = result.get("nodepools")
            if isinstance(pools, (list, tuple)):
                result["nodepools"] = [
                    {**cast("Mapping[str, object]", pool), "configs": [dict(e) for e in rule]}
                    if isinstance(pool, Mapping) and "configs" not in pool
                    else pool
                    for pool in cast("Sequence[object]", pools)
                ]
            continue
        updated = assigned(result, lock.path, lock.value)
        if updated is None:
            problems.append(
                f"{lock.path}: the flavor locks it to {_show(lock.value)}, but the cluster has no "
                f"{lock.path.parent}"
            )
        else:
            result = updated
    return result, problems
