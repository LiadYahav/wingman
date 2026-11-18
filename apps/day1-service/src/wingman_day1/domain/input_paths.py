"""Template-input paths: the grammar locks and problems use (ADR-0026, ADR-0029).

A path names one template input the way the create form addresses it::

    path  := name ( "." name | "[" index "]" )*
    name  := [A-Za-z_][A-Za-z0-9_]*       an identifier, as every input name is
    index := "0" | [1-9][0-9]{0,2} | "*"  a list position (no leading zero, below 1000),
                                          or every position

at most 253 characters, with no spaces: ``owner_merkaz``,
``nodepools[0].configs``, ``nodepools[*].configs``. :class:`InputPath`
parses and prints it; cluster file keys (``nodepool[0].nodeLabels``) are
written the same way, and a key that is no name in quotes
(``nodepool[0].annotations["redbull.io/scale-down-policy"]``, printed only).
:func:`lookup` and :func:`assigned` read and set the
value a path names in a mapping of inputs.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

MAX_PATH_LENGTH: Final = 253

_HEAD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STEP = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(0|[1-9][0-9]{0,2}|\*)\]")


class Every:
    """The ``[*]`` of a rule: every position of a list."""

    __slots__ = ()

    def __repr__(self) -> str:
        """``EVERY``, as the constant is named."""
        return "EVERY"


EVERY: Final = Every()
"""The segment ``[*]`` parses to."""

Segment = str | int | Every


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
            elif not _HEAD.fullmatch(str(segment)):
                out += f'["{segment}"]'  # a file key such as an annotation's
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
