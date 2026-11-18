"""The edits Wingman makes to a cluster file's values, and the check each must pass (ADR-0037).

``cluster_text`` makes an edit in the file's text; before anything is
written the edited text must parse to exactly the old values with the
intended changes (:func:`expected_values`, :func:`check_edited`), keep every
line from the CI marker on byte for byte, and keep every comment line that
is not in a removed entry (:func:`keeps_comments`).
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from wingman_day1.domain.cluster_file import load_values
from wingman_day1.domain.errors import InvalidClusterFileError, UneditableFileError
from wingman_day1.domain.locks import InputPath, entry_key
from wingman_day1.domain.yaml_lines import Line, split_lines

CI_MARKER: Final = "# === Added by CI ==="
"""The line the day1 CI writes above its block; it and every line after it are never edited."""


def frozen_from(lines: Sequence[Line]) -> int:
    """The index of the CI marker line, or ``len(lines)`` when the file has none."""
    return next((i for i, line in enumerate(lines) if line.stripped == CI_MARKER), len(lines))


@dataclass(frozen=True, slots=True)
class SetValue:
    """Set the value at a file key: ``owner.<x>``, ``platform``, ``nodepool[i].<key>``."""

    key: InputPath
    value: object


@dataclass(frozen=True, slots=True)
class SetConfigs:
    """Make a nodepool's ``configs`` name exactly ``names`` (a multiset, in any order).

    Entries that stay keep their lines, in the file's order; the others are
    removed; missing names are added after the last entry, in ``names`` order.
    """

    index: int
    names: tuple[str, ...]


Edit = SetValue | SetConfigs


def file_pool(values: dict[str, object], index: int) -> dict[str, object]:
    """``nodepool[index]`` of parsed values; ``UneditableFileError`` when the file has none."""
    pools = values.get("nodepool")
    if not isinstance(pools, list) or index >= len(pools) or not isinstance(pools[index], dict):
        raise UneditableFileError("the cluster file changed shape", [f"no nodepool[{index}]"])
    return cast("dict[str, object]", pools[index])


def expected_values(values: Mapping[str, object], edits: Sequence[Edit]) -> dict[str, object]:
    """``values`` with ``edits`` applied as data: what the edited text must parse to."""
    result = copy.deepcopy(dict(values))
    for edit in edits:
        if isinstance(edit, SetConfigs):
            pool = file_pool(result, edit.index)
            configs = pool.get("configs")
            have = list(cast("list[object]", configs)) if isinstance(configs, list) else []
            remaining = Counter(edit.names)
            kept: list[object] = []
            for raw in have:
                if remaining[entry_key(raw)] > 0:
                    remaining[entry_key(raw)] -= 1
                    kept.append(raw)
            for name in edit.names:
                if remaining[name] > 0:
                    kept.append({"name": name})
                    remaining[name] -= 1
            if kept or "configs" in pool:
                pool["configs"] = kept
            continue
        segments = edit.key.segments
        if segments[0] == "owner":
            owner = result.get("owner")
            if not isinstance(owner, dict):
                owner = {}
                result["owner"] = owner
            cast("dict[str, object]", owner)[str(segments[1])] = edit.value
        elif segments[0] == "nodepool":
            file_pool(result, cast("int", segments[1]))[str(segments[2])] = copy.deepcopy(
                edit.value
            )
        else:
            result[str(segments[0])] = edit.value
    return result


def _same(a: object, b: object) -> bool:
    """Equal, with types (``"3"`` is not ``3``, ``True`` is not ``1``); mapping order is free."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        left, right = cast("dict[object, object]", a), cast("dict[object, object]", b)
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    if isinstance(a, list):
        left_items, right_items = cast("list[object]", a), cast("list[object]", b)
        return len(left_items) == len(right_items) and all(
            _same(x, y) for x, y in zip(left_items, right_items, strict=True)
        )
    return a == b


def check_edited(old: str, new: str, expected: Mapping[str, object]) -> list[str]:
    """Why ``new`` may not replace ``old``: it must parse to ``expected`` and keep the CI block."""
    problems: list[str] = []
    old_lines = split_lines(old)
    tail = "".join(line.body + line.ending for line in old_lines[frozen_from(old_lines) :])
    if not new.endswith(tail):
        problems.append(f"the block from {CI_MARKER!r} on would change")
    try:
        parsed = load_values(new)
    except InvalidClusterFileError as exc:
        problems.append(f"the edited file would not parse: {exc}")
    else:
        if not _same(parsed, dict(expected)):
            changed = sorted(
                str(k)
                for k in {*parsed, *expected}
                if not _same(parsed.get(k, ...), expected.get(k, ...))
            )
            problems.append(f"the edited file would hold other values under {', '.join(changed)}")
    return problems


def keeps_comments(lines: Sequence[Line], deleted: set[int], new: str) -> bool:
    """Every comment line outside a removed entry is still there, in the same order."""
    kept = iter(line.body for line in split_lines(new) if line.stripped.startswith("#"))
    return all(
        any(body == line.body for body in kept)
        for index, line in enumerate(lines)
        if index not in deleted and line.stripped.startswith("#")
    )
