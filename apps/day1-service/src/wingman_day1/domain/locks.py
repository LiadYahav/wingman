"""Flavor locks: a value the flavor fixes and every create must use (ADR-0026).

A flavor's ``spec.day1.values`` holds template inputs. Each one is a
**preset** (prefilled at create; the person creating the cluster may change
it) or **locked**: its path is in ``spec.day1.locked_paths``, the flavor's
value is what the cluster gets, and a create that sends another value for
that path is refused.

Paths
=====

A path names one template input the way the create form addresses it::

    path  := name ( "." name | "[" index "]" )*
    name  := [A-Za-z_][A-Za-z0-9_]*       an identifier, as every input name is
    index := "0" | [1-9][0-9]{0,2}        a list position: no leading zero, below 1000

at most 253 characters, with no spaces: ``owner_merkaz``,
``nodepools[0].configs``. :class:`InputPath` parses and prints it; cluster
file keys (``nodepool[0].nodeLabels``) are written the same way.

What can be locked
==================

Only what day1 drift can later compare with the cluster file. Each lockable
input and the file key the shared template writes it to:

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
==============================  ============================

A value can differ in form between the two sides: a ``{name: nm-conf,
hardware: <hw>}`` entry is ``{name: nm-conf-<clusterName>-<hw>}`` in the
file (``machine_configs.expand_network_configs``), and ``platform`` is
written only as ``platform: kubevirt``. The inputs Wingman sets for each
cluster (name, site, MCE, OpenShift version) are never lockable.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from wingman_day1.domain.template import LEGACY_IDENTITY_ALIASES, RESERVED_INPUTS

MAX_PATH_LENGTH: Final = 253
MAX_LOCKS: Final = 100

_HEAD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STEP = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(0|[1-9][0-9]{0,2})\]")

Segment = str | int


class InvalidPathError(ValueError):
    """A string that is not a template-input path."""


@dataclass(frozen=True, slots=True)
class InputPath:
    """A path to one template input (or one cluster-file key): names and list positions."""

    segments: tuple[Segment, ...]

    @classmethod
    def parse(cls, text: str) -> InputPath:
        """``nodepools[0].configs`` → ``("nodepools", 0, "configs")``.

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
            segments.append(name if name is not None else int(index))
            position = step.end()
        return cls(tuple(segments))

    def __str__(self) -> str:
        """The path as written: ``nodepools[0].configs``."""
        out = ""
        for segment in self.segments:
            if isinstance(segment, int):
                out += f"[{segment}]"
            else:
                out += f".{segment}" if out else segment
        return out

    @property
    def parent(self) -> InputPath:
        """The path without its last segment."""
        return InputPath(self.segments[:-1])


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


MISSING: Final = _Missing()
"""What :func:`lookup` returns for a path that leads nowhere."""


def lookup(root: Mapping[str, object], path: InputPath) -> object:
    """The value at ``path``, or ``MISSING``."""
    current: object = root
    for segment in path.segments:
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
            if segment not in mapping:
                return MISSING
            current = mapping[segment]
    return current


def assigned(
    root: Mapping[str, object], path: InputPath, value: object
) -> dict[str, object] | None:
    """A copy of ``root`` with ``value`` at ``path``; ``None`` when the path's parent is missing.

    Only the containers along the path are copied; ``root`` is not changed.
    """

    def put(node: object, segments: tuple[Segment, ...]) -> object:
        segment, rest = segments[0], segments[1:]
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
        if rest and segment not in mapping:
            return MISSING
        child = put(mapping[segment], rest) if rest else value
        if child is MISSING:
            return MISSING
        mapping[segment] = child
        return mapping

    result = put(root, path.segments)
    return None if result is MISSING else cast("dict[str, object]", result)


# ── The lockable inputs and their cluster-file keys ──────────────────────────

_ANY_INDEX: Final = None


@dataclass(frozen=True, slots=True)
class Lockable:
    """One lockable input shape and the file key it is written to; ``None`` is any position."""

    input: tuple[str | None, ...]
    file_key: tuple[str | None, ...]

    def matches(self, path: InputPath) -> bool:
        """Whether ``path`` has this shape."""
        return len(path.segments) == len(self.input) and all(
            isinstance(s, int) if want is _ANY_INDEX else s == want
            for s, want in zip(path.segments, self.input, strict=True)
        )

    def file_path(self, path: InputPath) -> InputPath:
        """The file key for ``path`` (which must match), with its positions."""
        positions = iter(s for s in path.segments if isinstance(s, int))
        return InputPath(tuple(next(positions) if k is _ANY_INDEX else k for k in self.file_key))

    def __str__(self) -> str:
        """The shape as the docs write it: ``nodepools[<i>].configs``."""
        out = ""
        for k in self.input:
            out += "[<i>]" if k is _ANY_INDEX else (f".{k}" if out else k)
        return out


LOCKABLE: Final = (
    Lockable(("owner_merkaz",), ("owner", "merkaz")),
    Lockable(("owner_anaf",), ("owner", "anaf")),
    Lockable(("owner_mador",), ("owner", "mador")),
    Lockable(("platform",), ("platform",)),
    Lockable(("nodepools", _ANY_INDEX, "replicas"), ("nodepool", _ANY_INDEX, "replicas")),
    Lockable(("nodepools", _ANY_INDEX, "configs"), ("nodepool", _ANY_INDEX, "configs")),
    Lockable(("nodepools", _ANY_INDEX, "node_labels"), ("nodepool", _ANY_INDEX, "nodeLabels")),
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


# ── Locks at flavor save and at create ───────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Lock:
    """A locked path and the value the flavor fixes it to."""

    path: InputPath
    value: object


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


def lock_problems(locked_paths: Sequence[str], values: Mapping[str, object]) -> list[str]:
    """Why ``locked_paths`` cannot be saved with ``values``; empty when they can.

    Each path must parse, be lockable, appear once, and have a value in
    ``values`` (a lock is a value the flavor fixes, so a lock without one
    fixes nothing).
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
        if lookup(values, path) is MISSING:
            problems.append(
                f"locked_paths: {path} is locked but spec.day1.values sets no value for it"
            )
    return problems


def enforced_locks(locked_paths: Sequence[str], values: Mapping[str, object]) -> tuple[Lock, ...]:
    """The locks a create enforces: each lockable path once, with its value in ``values``.

    A spec saved before locks were enforced may list paths that break the
    save rules (:func:`lock_problems` reports them); those are not enforced.
    """
    locks: dict[InputPath, Lock] = {}
    for text in locked_paths:
        path = _parse(text)
        if isinstance(path, str) or _shape_problem(path) is not None:
            continue
        value = lookup(values, path)
        if value is not MISSING:
            locks[path] = Lock(path, value)
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


def lock_conflicts(
    variables: Mapping[str, object], locks: Sequence[Lock], *, flavor: str
) -> list[str]:
    """Each locked path a create sends a different value for."""
    problems: list[str] = []
    for lock in locks:
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
    on ``nodepools[2].replicas`` needs a third nodepool to exist.
    """
    result = dict(inputs)
    problems: list[str] = []
    for lock in locks:
        updated = assigned(result, lock.path, lock.value)
        if updated is None:
            problems.append(
                f"{lock.path}: the flavor locks it to {_show(lock.value)}, but the cluster has no "
                f"{lock.path.parent}"
            )
        else:
            result = updated
    return result, problems
