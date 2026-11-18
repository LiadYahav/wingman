"""Line-level YAML editing: a file's lines, a key's block, a list's items, patches.

The cluster file editor (``cluster_text``, ADR-0037) changes a file in its
text so every other line stays byte for byte. These are its parts: the file
as :class:`Line` objects that join back to the same text, a key's line
(:class:`KeyLine`, with its value and comment apart), the lines a key's value
takes (:class:`Block`), a block sequence's items (:class:`Item`), and the
replacements, deletions and insertions made on the original lines
(:class:`Patch`). New values are written as the shared template writes them
(:func:`render_value`, :func:`plain`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

import yaml

from wingman_day1.domain.errors import UneditableFileError

_KEY = re.compile(r"^(?P<lead> *(?:- +)?)(?P<key>[A-Za-z_][A-Za-z0-9_.\-/]*):(?=\s|$)(?P<rest>.*)$")
DEFAULT_STEP: Final = 2


# ── Lines ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Line:
    """One line of the file, its text and its ending apart."""

    body: str
    """The line without its ending."""
    ending: str
    """``\\n``, ``\\r\\n``, or ``""`` for a last line without one."""

    @property
    def stripped(self) -> str:
        """The line without the whitespace around it."""
        return self.body.strip()

    @property
    def indent(self) -> int:
        """How many spaces it starts with."""
        return len(self.body) - len(self.body.lstrip(" "))

    @property
    def is_content(self) -> bool:
        """Neither blank nor a comment."""
        text = self.stripped
        return bool(text) and not text.startswith("#")

    @property
    def is_dash(self) -> bool:
        """A sequence item's first line: ``-`` or ``- ...``."""
        text = self.body.lstrip(" ")
        return text == "-" or text.startswith("- ")


def split_lines(content: str) -> list[Line]:
    """The file's lines, each with its own ending, so joining them gives ``content`` back."""
    lines: list[Line] = []
    parts = content.split("\n")
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if last and part == "":
            break
        if not last and part.endswith("\r"):
            lines.append(Line(part[:-1], "\r\n"))
        else:
            lines.append(Line(part, "" if last else "\n"))
    return lines


def _newline(lines: Sequence[Line]) -> str:
    return next((line.ending for line in lines if line.ending), "\n")


def _split_comment(rest: str) -> tuple[str, str]:
    """The text after ``key:`` as (value, comment with the whitespace before it)."""
    quote: str | None = None
    index = 0
    while index < len(rest):
        char = rest[index]
        if quote is not None:
            if char == quote:
                if quote == "'" and rest[index + 1 : index + 2] == "'":
                    index += 2
                    continue
                quote = None
            elif char == "\\" and quote == '"':
                index += 2
                continue
        elif char in "'\"" and not rest[:index].strip():
            quote = char
        elif char == "#" and index > 0 and rest[index - 1] in " \t":
            start = index
            while start > 0 and rest[start - 1] in " \t":
                start -= 1
            return rest[:start], rest[start:]
        index += 1
    return rest, ""


@dataclass(frozen=True, slots=True)
class KeyLine:
    """A ``key: value  # comment`` line, taken apart."""

    index: int
    lead: str
    """The indentation, and ``- `` on an item's first line."""
    key: str
    value: str
    comment: str

    @property
    def column(self) -> int:
        """Where the key starts."""
        return len(self.lead)


def key_line(lines: Sequence[Line], index: int) -> KeyLine | None:
    """The key on line ``index``; ``None`` when the line holds none."""
    match = _KEY.match(lines[index].body)
    if match is None:
        return None
    value, comment = _split_comment(match["rest"])
    return KeyLine(index, match["lead"], match["key"], value.strip(), comment)


# ── Blocks: a key's lines, a sequence's items ────────────────────────────────


@dataclass(frozen=True, slots=True)
class Block:
    """A key and the lines its value takes."""

    key: KeyLine
    end: int
    """One past the block's last content line (trailing comments and blanks are not its)."""

    @property
    def children(self) -> range:
        """The lines after the key's own, up to the block's end."""
        return range(self.key.index + 1, self.end)


def block_end(lines: Sequence[Line], key: KeyLine, stop: int) -> int:
    """One past the last content line that belongs to ``key``'s value.

    It holds lines indented deeper than the key and, for a sequence written
    in production's compact style, ``- `` lines at the key's own column.
    """
    end = key.index + 1
    for index in range(key.index + 1, stop):
        line = lines[index]
        if not line.is_content:
            continue
        if line.indent > key.column or (line.indent == key.column and line.is_dash):
            end = index + 1
            continue
        break
    return end


def keys_at(
    lines: Sequence[Line], start: int, stop: int, column: int, *, first: int | None = None
) -> list[KeyLine]:
    """The keys of one mapping: content lines at ``column`` that are not ``- `` items.

    ``first`` is an item's ``- `` line, whose own key sits at ``column`` too.
    """
    found: list[KeyLine] = []
    for index in range(start, stop):
        line = lines[index]
        if not line.is_content:
            continue
        own = index == first
        if line.indent < column and not own:
            break
        if (line.indent == column and not line.is_dash) or own:
            key = key_line(lines, index)
            if key is not None and key.column == column:
                found.append(key)
    return found


def find_key(lines: Sequence[Line], keys: Sequence[KeyLine], name: str) -> KeyLine | None:
    """The key called ``name`` among ``keys``; ``UneditableFileError`` when it is there twice."""
    matches = [k for k in keys if k.key == name]
    if len(matches) > 1:
        raise UneditableFileError(
            "the cluster file lists a key twice", [f"{name} appears {len(matches)} times"]
        )
    return matches[0] if matches else None


@dataclass(frozen=True, slots=True)
class Item:
    """One item of a block sequence."""

    start: int
    """The item's ``- `` line."""
    end: int
    """One past its last content line."""
    column: int
    """Where its keys start."""


def list_items(lines: Sequence[Line], block: Block, what: str) -> tuple[list[Item], int]:
    """A block sequence's items and the column of their ``-``."""
    content = [i for i in block.children if lines[i].is_content]
    if not content:
        return [], block.key.column + DEFAULT_STEP
    dash = lines[content[0]].indent
    starts = [i for i in content if lines[i].indent == dash and lines[i].is_dash]
    if not starts or starts[0] != content[0]:
        raise UneditableFileError(
            f"{what} is not a list Wingman can edit", [f"line {content[0] + 1} is not a '- ' item"]
        )
    items: list[Item] = []
    for number, start in enumerate(starts):
        stop = starts[number + 1] if number + 1 < len(starts) else block.end
        last = max(i for i in content if start <= i < stop)
        body = lines[start].body
        after = body[dash + 1 :]
        if after.strip():
            column = dash + 1 + (len(after) - len(after.lstrip(" ")))
        else:
            nested = [i for i in content if start < i < stop]
            column = lines[nested[0]].indent if nested else dash + DEFAULT_STEP
        items.append(Item(start, last + 1, column))
    return items, dash


# ── Patches on the original lines ────────────────────────────────────────────


@dataclass(slots=True)
class Patch:
    """Changes to the original lines, rendered together; other lines keep their bytes."""

    lines: Sequence[Line]
    replaced: dict[int, str] = field(default_factory=dict)
    deleted: set[int] = field(default_factory=set)
    inserted: dict[int, list[str]] = field(default_factory=dict)
    """New lines to put before each original index (``len(lines)`` is the end)."""

    def replace(self, index: int, body: str) -> None:
        """Line ``index`` becomes ``body`` (its ending is kept)."""
        self.replaced[index] = body

    def delete(self, start: int, stop: int) -> None:
        """Lines ``start`` up to ``stop`` go."""
        self.deleted.update(range(start, stop))

    def insert(self, before: int, bodies: Sequence[str]) -> None:
        """New lines go before line ``before``, after any inserted there already."""
        self.inserted.setdefault(before, []).extend(bodies)

    def render(self) -> str:
        """The file with every change made, in the file's own line endings."""
        newline = _newline(self.lines)
        out: list[str] = []

        def emit(body: str, ending: str) -> None:
            if out and not out[-1].endswith("\n"):
                out[-1] += newline
            out.append(body + ending)

        for index, line in enumerate(self.lines):
            for body in self.inserted.get(index, []):
                emit(body, newline)
            if index in self.deleted:
                continue
            emit(self.replaced.get(index, line.body), line.ending)
        for body in self.inserted.get(len(self.lines), []):
            emit(body, newline)
        return "".join(out)


def plain(text: str) -> str:
    """``text`` as a YAML scalar: plain when it reads back as the same string, else quoted."""
    try:
        same = yaml.safe_load(f"k: {text}") == {"k": text}
    except yaml.YAMLError:
        same = False
    return text if same and text == text.strip() and "#" not in text else json.dumps(text)


def render_value(value: object) -> str:
    """A value as the shared template writes it: owners quoted, numbers bare, maps as JSON."""
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool) or value is None:
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)
