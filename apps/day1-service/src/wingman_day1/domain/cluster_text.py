"""Editing a cluster file's text so that everything else stays byte for byte (ADR-0034).

A cluster file is written by several hands: people (with their comments),
Wingman, the allocate-segment workflow (``vlanId``, ``dhcp_values``) and the
day1 CI, which appends its block under ``# === Added by CI ===`` (``mcFiles``,
``mcConfigMap``). The platform's own scripts edit these files line by line
for that reason; a YAML round trip would reflow and re-quote all of it, drop
the comments and rewrite the CI's block. Wingman edits lines the same way:

- :func:`with_header` sets Wingman's comment header (``# specName:`` ...,
  ADR-0012) in the leading comment block and changes no other line;
- :func:`edit_values` sets the values a flavor locks: ``owner.<x>``,
  ``platform``, a nodepool's ``replicas``, ``nodeLabels`` and ``configs``.
  A replaced value keeps its line's comment; a config entry that stays keeps
  its line; a removed entry takes only its own lines; new lines copy the
  indentation the file already uses.

Then each edit checks its own work before anything is written: the edited
text must parse, hold exactly the old values with the intended changes (no
type, quoting or ordering surprise), and keep every line from the CI marker
on byte for byte. A file whose layout the editor cannot handle (a flow-style
``nodepool``, a value spread over lines) is refused with the reason, never
written approximately: a person edits it by hand.

Nothing here touches ``vlanId``, ``dhcp_values``, ``mcFiles`` or
``mcConfigMap``, and nothing at or below the CI marker is ever edited.
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, cast

import yaml

from wingman_day1.domain.cluster_file import (
    Provenance,
    is_header_line,
    load_values,
    provenance_lines,
    read_provenance,
)
from wingman_day1.domain.errors import InvalidClusterFileError, UneditableFileError
from wingman_day1.domain.locks import InputPath, entry_key

CI_MARKER: Final = "# === Added by CI ==="
"""The line the day1 CI writes above its block; it and every line after it are never edited."""

_KEY = re.compile(r"^(?P<lead> *(?:- +)?)(?P<key>[A-Za-z_][A-Za-z0-9_.\-/]*):(?=\s|$)(?P<rest>.*)$")
_DEFAULT_STEP: Final = 2


# ── Lines ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Line:
    body: str
    """The line without its ending."""
    ending: str
    """``\\n``, ``\\r\\n``, or ``""`` for a last line without one."""

    @property
    def stripped(self) -> str:
        return self.body.strip()

    @property
    def indent(self) -> int:
        return len(self.body) - len(self.body.lstrip(" "))

    @property
    def is_content(self) -> bool:
        text = self.stripped
        return bool(text) and not text.startswith("#")

    @property
    def is_dash(self) -> bool:
        text = self.body.lstrip(" ")
        return text == "-" or text.startswith("- ")


def _split(content: str) -> list[_Line]:
    """The file's lines, each with its own ending, so joining them gives ``content`` back."""
    lines: list[_Line] = []
    parts = content.split("\n")
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if last and part == "":
            break
        if not last and part.endswith("\r"):
            lines.append(_Line(part[:-1], "\r\n"))
        else:
            lines.append(_Line(part, "" if last else "\n"))
    return lines


def _newline(lines: Sequence[_Line]) -> str:
    return next((line.ending for line in lines if line.ending), "\n")


def _frozen_from(lines: Sequence[_Line]) -> int:
    """The index of the CI marker line, or ``len(lines)`` when the file has none."""
    return next((i for i, line in enumerate(lines) if line.stripped == CI_MARKER), len(lines))


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
class _KeyLine:
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


def _key_line(lines: Sequence[_Line], index: int) -> _KeyLine | None:
    match = _KEY.match(lines[index].body)
    if match is None:
        return None
    value, comment = _split_comment(match["rest"])
    return _KeyLine(index, match["lead"], match["key"], value.strip(), comment)


# ── Blocks: a key's lines, a sequence's items ────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Block:
    key: _KeyLine
    end: int
    """One past the block's last content line (trailing comments and blanks are not its)."""

    @property
    def children(self) -> range:
        return range(self.key.index + 1, self.end)


def _block_end(lines: Sequence[_Line], key: _KeyLine, stop: int) -> int:
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


def _keys_at(
    lines: Sequence[_Line], start: int, stop: int, column: int, *, first: int | None = None
) -> list[_KeyLine]:
    """The keys of one mapping: content lines at ``column`` that are not ``- `` items.

    ``first`` is an item's ``- `` line, whose own key sits at ``column`` too.
    """
    found: list[_KeyLine] = []
    for index in range(start, stop):
        line = lines[index]
        if not line.is_content:
            continue
        own = index == first
        if line.indent < column and not own:
            break
        if (line.indent == column and not line.is_dash) or own:
            key = _key_line(lines, index)
            if key is not None and key.column == column:
                found.append(key)
    return found


def _find(lines: Sequence[_Line], keys: Sequence[_KeyLine], name: str) -> _KeyLine | None:
    matches = [k for k in keys if k.key == name]
    if len(matches) > 1:
        raise UneditableFileError(
            "the cluster file lists a key twice", [f"{name} appears {len(matches)} times"]
        )
    return matches[0] if matches else None


@dataclass(frozen=True, slots=True)
class _Item:
    start: int
    """The item's ``- `` line."""
    end: int
    """One past its last content line."""
    column: int
    """Where its keys start."""


def _items(lines: Sequence[_Line], block: _Block, what: str) -> tuple[list[_Item], int]:
    """A block sequence's items and the column of their ``-``."""
    content = [i for i in block.children if lines[i].is_content]
    if not content:
        return [], block.key.column + _DEFAULT_STEP
    dash = lines[content[0]].indent
    starts = [i for i in content if lines[i].indent == dash and lines[i].is_dash]
    if not starts or starts[0] != content[0]:
        raise UneditableFileError(
            f"{what} is not a list Wingman can edit", [f"line {content[0] + 1} is not a '- ' item"]
        )
    items: list[_Item] = []
    for number, start in enumerate(starts):
        stop = starts[number + 1] if number + 1 < len(starts) else block.end
        last = max(i for i in content if start <= i < stop)
        body = lines[start].body
        after = body[dash + 1 :]
        if after.strip():
            column = dash + 1 + (len(after) - len(after.lstrip(" ")))
        else:
            nested = [i for i in content if start < i < stop]
            column = lines[nested[0]].indent if nested else dash + _DEFAULT_STEP
        items.append(_Item(start, last + 1, column))
    return items, dash


# ── Patches on the original lines ────────────────────────────────────────────


@dataclass(slots=True)
class _Patch:
    lines: Sequence[_Line]
    replaced: dict[int, str] = field(default_factory=dict)
    deleted: set[int] = field(default_factory=set)
    inserted: dict[int, list[str]] = field(default_factory=dict)
    """New lines to put before each original index (``len(lines)`` is the end)."""

    def replace(self, index: int, body: str) -> None:
        self.replaced[index] = body

    def delete(self, start: int, stop: int) -> None:
        self.deleted.update(range(start, stop))

    def insert(self, before: int, bodies: Sequence[str]) -> None:
        self.inserted.setdefault(before, []).extend(bodies)

    def render(self) -> str:
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


def _plain(text: str) -> str:
    """``text`` as a YAML scalar: plain when it reads back as the same string, else quoted."""
    try:
        same = yaml.safe_load(f"k: {text}") == {"k": text}
    except yaml.YAMLError:
        same = False
    return text if same and text == text.strip() and "#" not in text else json.dumps(text)


def _render(value: object) -> str:
    """A value as the shared template writes it: owners quoted, numbers bare, maps as JSON."""
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool) or value is None:
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


# ── The header ───────────────────────────────────────────────────────────────


def with_header(content: str, provenance: Provenance) -> str:
    """``content`` with Wingman's header set to ``provenance``; no other line changes.

    The header lives in the leading comment block (the lines before the first
    one that is not a comment). Its lines are replaced where the first of them
    is, or put first; every other comment keeps its place and bytes.
    """
    lines = _split(content)
    leading = 0
    while leading < len(lines) and lines[leading].stripped.startswith("#"):
        leading += 1
    header = [i for i in range(leading) if is_header_line(lines[i].body)]
    patch = _Patch(lines)
    for index in header:
        patch.delete(index, index + 1)
    patch.insert(header[0] if header else 0, provenance_lines(provenance))
    edited = patch.render()
    problems = _check(content, edited, _values_or_refuse(content))
    if _without_header(edited) != _without_header(content):
        problems.append("a line other than the flavor header would change")
    wanted = Provenance(provenance.spec_name, provenance.spec_version, provenance.requested_addons)
    if read_provenance(edited) != wanted:
        problems.append("the edited header would not read back as written")
    if problems:
        raise UneditableFileError("Wingman could not write the flavor header safely", problems)
    return edited


def _without_header(content: str) -> str:
    """``content`` without Wingman's header lines in its leading comment block."""
    lines = _split(content)
    leading = 0
    while leading < len(lines) and lines[leading].stripped.startswith("#"):
        leading += 1
    return "".join(
        line.body + line.ending
        for index, line in enumerate(lines)
        if index >= leading or not is_header_line(line.body)
    )


# ── Values ───────────────────────────────────────────────────────────────────


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


def _values_or_refuse(content: str) -> dict[str, object]:
    try:
        return load_values(content)
    except InvalidClusterFileError as exc:
        raise UneditableFileError(
            "the cluster file does not parse, so Wingman cannot edit it", exc.problems
        ) from exc


@dataclass(slots=True)
class _Editor:
    lines: Sequence[_Line]
    stop: int
    patch: _Patch

    def top_keys(self) -> list[_KeyLine]:
        return _keys_at(self.lines, 0, self.stop, 0)

    def top(self, name: str) -> _KeyLine | None:
        return _find(self.lines, self.top_keys(), name)

    def block(self, key: _KeyLine) -> _Block:
        return _Block(key, _block_end(self.lines, key, self.stop))

    def scalar(self, key: _KeyLine, value: str, what: str) -> None:
        if not key.value or any(self.lines[i].is_content for i in self.block(key).children):
            raise UneditableFileError(
                f"{what} is not a one-line value Wingman can replace",
                [f"line {key.index + 1}: {self.lines[key.index].stripped}"],
            )
        self.patch.replace(key.index, f"{key.lead}{key.key}: {value}{key.comment}")

    def body_start(self) -> int:
        """Where new top-level keys go first: before the first key and its comments."""
        keys = self.top_keys()
        return self._attached(keys[0].index) if keys else self.stop

    def _attached(self, index: int) -> int:
        """``index`` moved up over the comment lines directly above it.

        Never into the leading comment block: Wingman's header lives there,
        and a key above it would stop it being read (ADR-0012).
        """
        floor = 0
        while floor < len(self.lines) and self.lines[floor].stripped.startswith("#"):
            floor += 1
        while index > floor and self.lines[index - 1].stripped.startswith("#"):
            index -= 1
        return max(index, min(floor, self.stop))

    # ── top level ──

    def set_owners(self, owners: Mapping[str, object]) -> None:
        owner = self.top("owner")
        if owner is None:
            lines = [f"{' ' * _DEFAULT_STEP}{k}: {_render(v)}" for k, v in owners.items()]
            self.patch.insert(self.body_start(), ["owner:", *lines, ""])
            return
        if owner.value:
            raise UneditableFileError(
                "owner is not a block mapping Wingman can edit",
                [f"line {owner.index + 1}: {self.lines[owner.index].stripped}"],
            )
        block = self.block(owner)
        content = [i for i in block.children if self.lines[i].is_content]
        column = self.lines[content[0]].indent if content else _DEFAULT_STEP
        children = _keys_at(self.lines, owner.index + 1, block.end, column)
        missing: list[str] = []
        for child, value in owners.items():
            found = _find(self.lines, children, child)
            if found is None:
                missing.append(f"{' ' * column}{child}: {_render(value)}")
            else:
                self.scalar(found, _render(value), f"owner.{child}")
        if missing:
            self.patch.insert(block.end, missing)

    def set_platform(self, value: object) -> None:
        rendered = _plain(str(value))
        found = self.top("platform")
        if found is not None:
            self.scalar(found, rendered, "platform")
            return
        nodepool = self.top("nodepool")
        where = self._attached(nodepool.index) if nodepool else self.body_start()
        self.patch.insert(where, [f"platform: {rendered}", ""])

    # ── nodepools ──

    def item(self, index: int) -> _Item:
        nodepool = self.top("nodepool")
        if nodepool is None or nodepool.value:
            raise UneditableFileError(
                "nodepool is not a block list Wingman can edit",
                ["the file has no nodepool list" if nodepool is None else "it is written inline"],
            )
        items, _ = _items(self.lines, self.block(nodepool), "nodepool")
        if index >= len(items):
            raise UneditableFileError(
                "the cluster file changed shape", [f"it has no nodepool[{index}]"]
            )
        return items[index]

    def item_keys(self, item: _Item) -> list[_KeyLine]:
        return _keys_at(self.lines, item.start, item.end, item.column, first=item.start)

    def set_item_value(self, index: int, name: str, value: object) -> None:
        item = self.item(index)
        found = _find(self.lines, self.item_keys(item), name)
        rendered = _render(value)
        if found is None:
            self.patch.insert(item.end, [f"{' ' * item.column}{name}: {rendered}"])
            return
        if name == "replicas":
            self.scalar(found, rendered, f"nodepool[{index}].{name}")
            return
        block = self.block(found)
        for child in block.children:
            if self.lines[child].is_content:
                self.patch.delete(child, child + 1)
        self.patch.replace(found.index, f"{found.lead}{found.key}: {rendered}{found.comment}")

    def set_configs(self, index: int, names: Sequence[str], parsed: Sequence[object]) -> None:
        item = self.item(index)
        keys = self.item_keys(item)
        found = _find(self.lines, keys, "configs")
        step = self._config_step()
        if found is None:
            if names:
                lines = [f"{' ' * item.column}configs:"]
                lines += [f"{' ' * (item.column + step)}- name: {_plain(n)}" for n in names]
                self.patch.insert(item.end, lines)
            return
        block = self.block(found)
        if found.value:
            # An inline list ([] or flow): rewritten as the file's block style.
            if not names:
                self.patch.replace(found.index, f"{found.lead}configs: []{found.comment}")
                return
            self.patch.replace(found.index, f"{found.lead}configs:{found.comment}")
            column = found.column + step
            self.patch.insert(
                found.index + 1, [f"{' ' * column}- name: {_plain(n)}" for n in names]
            )
            return
        entries, dash = _items(self.lines, block, f"nodepool[{index}].configs")
        if len(entries) != len(parsed):
            raise UneditableFileError(
                f"nodepool[{index}].configs is not a list Wingman can edit",
                [f"{len(entries)} '- ' lines for {len(parsed)} entries"],
            )
        remaining = Counter(names)
        last_kept: int | None = None
        for entry, raw in zip(entries, parsed, strict=True):
            name = entry_key(raw)
            if remaining[name] > 0:
                remaining[name] -= 1
                last_kept = entry.end
            else:
                self.patch.delete(entry.start, entry.end)
        added: list[str] = []
        for name in names:
            if remaining[name] > 0:
                added.append(name)
                remaining[name] -= 1
        if not names:
            self.patch.replace(found.index, f"{found.lead}configs: []{found.comment}")
            return
        where = last_kept if last_kept is not None else found.index + 1
        self.patch.insert(where, [f"{' ' * dash}- name: {_plain(n)}" for n in added])

    def _config_step(self) -> int:
        """How far the file indents a ``configs`` list from its key (production: 0)."""
        nodepool = self.top("nodepool")
        if nodepool is None or nodepool.value:
            return _DEFAULT_STEP
        items, _ = _items(self.lines, self.block(nodepool), "nodepool")
        for item in items:
            found = _find(self.lines, self.item_keys(item), "configs")
            if found is None or found.value:
                continue
            content = [i for i in self.block(found).children if self.lines[i].is_content]
            if content:
                return self.lines[content[0]].indent - found.column
        return _DEFAULT_STEP


def _pool(values: dict[str, object], index: int) -> dict[str, object]:
    pools = values.get("nodepool")
    if not isinstance(pools, list) or index >= len(pools) or not isinstance(pools[index], dict):
        raise UneditableFileError("the cluster file changed shape", [f"no nodepool[{index}]"])
    return cast("dict[str, object]", pools[index])


def _expected(values: Mapping[str, object], edits: Sequence[Edit]) -> dict[str, object]:
    """``values`` with ``edits`` applied as data: what the edited text must parse to."""
    result = copy.deepcopy(dict(values))
    for edit in edits:
        if isinstance(edit, SetConfigs):
            pool = _pool(result, edit.index)
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
            _pool(result, cast("int", segments[1]))[str(segments[2])] = copy.deepcopy(edit.value)
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


def _check(old: str, new: str, expected: Mapping[str, object]) -> list[str]:
    """Why ``new`` may not replace ``old``: it must parse to ``expected`` and keep the CI block."""
    problems: list[str] = []
    old_lines = _split(old)
    tail = "".join(line.body + line.ending for line in old_lines[_frozen_from(old_lines) :])
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


def _keeps_comments(lines: Sequence[_Line], deleted: set[int], new: str) -> bool:
    """Every comment line outside a removed entry is still there, in the same order."""
    kept = iter(line.body for line in _split(new) if line.stripped.startswith("#"))
    return all(
        any(body == line.body for body in kept)
        for index, line in enumerate(lines)
        if index not in deleted and line.stripped.startswith("#")
    )


def edit_values(content: str, edits: Sequence[Edit]) -> str:
    """``content`` with ``edits`` made in its text, every other line kept byte for byte.

    Raises ``UneditableFileError`` when the file does not parse, its layout
    is not one the editor handles, or the result would not hold exactly the
    old values with these changes.
    """
    values = _values_or_refuse(content)
    lines = _split(content)
    editor = _Editor(lines, _frozen_from(lines), _Patch(lines))
    owners = {
        str(e.key.segments[1]): e.value
        for e in edits
        if isinstance(e, SetValue) and e.key.segments[0] == "owner" and len(e.key.segments) == 2
    }
    if owners:
        editor.set_owners(owners)
    for edit in edits:
        if isinstance(edit, SetConfigs):
            configs = _pool(values, edit.index).get("configs")
            parsed = cast("list[object]", configs) if isinstance(configs, list) else []
            editor.set_configs(edit.index, edit.names, parsed)
            continue
        segments = edit.key.segments
        if segments[0] == "owner" and len(segments) == 2:
            continue
        if segments == ("platform",):
            editor.set_platform(edit.value)
        elif segments[0] == "nodepool" and len(segments) == 3 and isinstance(segments[1], int):
            editor.set_item_value(segments[1], str(segments[2]), edit.value)
        else:
            raise UneditableFileError(
                "Wingman does not edit that key", [f"{edit.key} is not a lockable file key"]
            )
    edited = editor.patch.render()
    problems = _check(content, edited, _expected(values, edits))
    if not _keeps_comments(lines, editor.patch.deleted, edited):
        problems.append("a comment line would be lost")
    if problems:
        raise UneditableFileError("Wingman could not edit the cluster file safely", problems)
    return edited
