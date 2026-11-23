"""Editing a cluster file's text so that everything else stays byte for byte (ADR-0037).

A cluster file is written by several hands: people (with their comments),
Wingman, the provision-cluster workflow (``vlanId``, ``dhcp_values``) and the
day1 CI, which appends its block under ``# === Added by CI ===`` (``mcFiles``,
``mcConfigMap``). The platform's own scripts edit these files line by line
for that reason; a YAML round trip would reflow and re-quote all of it, drop
the comments and rewrite the CI's block. Wingman edits lines the same way:

- :func:`with_header` sets Wingman's comment header (``# specName:`` ...,
  ADR-0012) in the leading comment block and changes no other line;
- :func:`edit_values` sets the values a flavor locks: ``owner.<x>``,
  ``platform``, the image mirrors (``imageContentSources``,
  ``disableIdmsMerge``), a nodepool's ``replicas``, ``nodeLabels``, ``configs``
  and the scale-down policy in its ``annotations`` (ADR-0062).
  A replaced value keeps its line's comment; a config entry that stays keeps
  its line; a removed entry takes only its own lines; new lines copy the
  indentation the file already uses.

Then each edit checks its own work before anything is written: the edited
text must parse, hold exactly the old values with the intended changes (no
type, quoting or ordering surprise), and keep every line from the CI marker
on byte for byte. A file whose layout the editor cannot handle (a flow-style
``nodepool``, a value spread over lines) is refused with the reason, never
written approximately: a person edits it by hand. The line-level parts (a
key's block, a list's items, patches on the original lines) are in
``yaml_lines``; the edits and that check are in ``cluster_edits``.

Nothing here touches ``vlanId``, ``dhcp_values``, ``mcFiles``,
``mcConfigMap`` or ``tuningConfigmap``, and nothing at or below the CI marker is ever edited.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from wingman_day1.domain.cluster_edits import (
    Edit,
    SetConfigs,
    SetValue,
    check_edited,
    expected_values,
    file_pool,
    frozen_from,
    keeps_comments,
)
from wingman_day1.domain.cluster_file import (
    Provenance,
    is_header_line,
    load_values,
    provenance_lines,
    read_provenance,
)
from wingman_day1.domain.errors import InvalidClusterFileError, UneditableFileError
from wingman_day1.domain.image_mirrors import MIRROR_FILE_KEYS
from wingman_day1.domain.locks import entry_key
from wingman_day1.domain.scale_down_policy import ANNOTATIONS
from wingman_day1.domain.yaml_lines import (
    DEFAULT_STEP,
    Block,
    Item,
    KeyLine,
    Line,
    Patch,
    block_end,
    find_key,
    keys_at,
    list_items,
    plain,
    render_value,
    split_lines,
)

# ── The header ───────────────────────────────────────────────────────────────


def with_header(content: str, provenance: Provenance) -> str:
    """``content`` with Wingman's header set to ``provenance``; no other line changes.

    The header lives in the leading comment block (the lines before the first
    one that is not a comment). Its lines are replaced where the first of them
    is, or put first; every other comment keeps its place and bytes.
    """
    lines = split_lines(content)
    leading = 0
    while leading < len(lines) and lines[leading].stripped.startswith("#"):
        leading += 1
    header = [i for i in range(leading) if is_header_line(lines[i].body)]
    patch = Patch(lines)
    for index in header:
        patch.delete(index, index + 1)
    patch.insert(header[0] if header else 0, provenance_lines(provenance))
    edited = patch.render()
    problems = check_edited(content, edited, values_or_refuse(content))
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
    lines = split_lines(content)
    leading = 0
    while leading < len(lines) and lines[leading].stripped.startswith("#"):
        leading += 1
    return "".join(
        line.body + line.ending
        for index, line in enumerate(lines)
        if index >= leading or not is_header_line(line.body)
    )


# ── Values ───────────────────────────────────────────────────────────────────


def values_or_refuse(content: str) -> dict[str, object]:
    """The file's values; ``UneditableFileError`` when it does not parse."""
    try:
        return load_values(content)
    except InvalidClusterFileError as exc:
        raise UneditableFileError(
            "the cluster file does not parse, so Wingman cannot edit it", exc.problems
        ) from exc


@dataclass(slots=True)
class _Editor:
    lines: Sequence[Line]
    stop: int
    patch: Patch

    def top_keys(self) -> list[KeyLine]:
        return keys_at(self.lines, 0, self.stop, 0)

    def top(self, name: str) -> KeyLine | None:
        return find_key(self.lines, self.top_keys(), name)

    def block(self, key: KeyLine) -> Block:
        return Block(key, block_end(self.lines, key, self.stop))

    def scalar(self, key: KeyLine, value: str, what: str) -> None:
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
            lines = [f"{' ' * DEFAULT_STEP}{k}: {render_value(v)}" for k, v in owners.items()]
            self.patch.insert(self.body_start(), ["owner:", *lines, ""])
            return
        if owner.value:
            raise UneditableFileError(
                "owner is not a block mapping Wingman can edit",
                [f"line {owner.index + 1}: {self.lines[owner.index].stripped}"],
            )
        block = self.block(owner)
        content = [i for i in block.children if self.lines[i].is_content]
        column = self.lines[content[0]].indent if content else DEFAULT_STEP
        children = keys_at(self.lines, owner.index + 1, block.end, column)
        missing: list[str] = []
        for child, value in owners.items():
            found = find_key(self.lines, children, child)
            if found is None:
                missing.append(f"{' ' * column}{child}: {render_value(value)}")
            else:
                self.scalar(found, render_value(value), f"owner.{child}")
        if missing:
            self.patch.insert(block.end, missing)

    def set_platform(self, value: object) -> None:
        rendered = plain(str(value))
        found = self.top("platform")
        if found is not None:
            self.scalar(found, rendered, "platform")
            return
        nodepool = self.top("nodepool")
        where = self._attached(nodepool.index) if nodepool else self.body_start()
        self.patch.insert(where, [f"platform: {rendered}", ""])

    def set_mirrors(self, name: str, value: object) -> None:
        """``imageContentSources`` as a block list, or ``disableIdmsMerge`` (ADR-0063).

        A key already there keeps its line and comment, and the comments in
        its block; its old content lines go. A new key goes above
        ``nodepool``, as the shared template writes it.
        """
        entries = _mirror_lines(value)
        found = self.top(name)
        if found is None:
            nodepool = self.top("nodepool")
            where = self._attached(nodepool.index) if nodepool else self.body_start()
            head = f"{name}:" if entries else f"{name}: {render_value(value)}"
            self.patch.insert(where, [head, *entries, ""])
            return
        for child in self.block(found).children:
            if self.lines[child].is_content:
                self.patch.delete(child, child + 1)
        value_text = "" if entries else f" {render_value(value)}"
        self.patch.replace(found.index, f"{found.lead}{found.key}:{value_text}{found.comment}")
        self.patch.insert(found.index + 1, entries)

    # ── nodepools ──

    def item(self, index: int) -> Item:
        nodepool = self.top("nodepool")
        if nodepool is None or nodepool.value:
            raise UneditableFileError(
                "nodepool is not a block list Wingman can edit",
                ["the file has no nodepool list" if nodepool is None else "it is written inline"],
            )
        items, _ = list_items(self.lines, self.block(nodepool), "nodepool")
        if index >= len(items):
            raise UneditableFileError(
                "the cluster file changed shape", [f"it has no nodepool[{index}]"]
            )
        return items[index]

    def item_keys(self, item: Item) -> list[KeyLine]:
        return keys_at(self.lines, item.start, item.end, item.column, first=item.start)

    def set_item_value(self, index: int, name: str, value: object) -> None:
        item = self.item(index)
        found = find_key(self.lines, self.item_keys(item), name)
        rendered = render_value(value)
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

    def set_annotation(self, index: int, name: str, value: object) -> None:
        """One key of a nodepool's ``annotations``; its other keys and comments stay.

        Without ``annotations`` the block is added at the entry's end, as the
        shared template writes it; ``annotations: {}`` becomes that block.
        """
        item = self.item(index)
        rendered = plain(str(value))  # as the template writes the policy
        found = find_key(self.lines, self.item_keys(item), ANNOTATIONS)
        if found is None:
            pad = " " * item.column
            lines = [f"{pad}{ANNOTATIONS}:", f"{pad}{' ' * DEFAULT_STEP}{name}: {rendered}"]
            self.patch.insert(item.end, lines)
            return
        where = f"nodepool[{index}].{ANNOTATIONS}"
        if found.value and found.value != "{}":
            raise UneditableFileError(
                f"{where} is not a block mapping Wingman can edit",
                [f"line {found.index + 1}: {self.lines[found.index].stripped}"],
            )
        block = self.block(found)
        content = [i for i in block.children if self.lines[i].is_content]
        column = self.lines[content[0]].indent if content else found.column + DEFAULT_STEP
        key = find_key(self.lines, keys_at(self.lines, found.index + 1, block.end, column), name)
        if found.value:
            self.patch.replace(found.index, f"{found.lead}{found.key}:{found.comment}")
        if key is None:
            self.patch.insert(block.end, [f"{' ' * column}{name}: {rendered}"])
        else:
            self.scalar(key, rendered, f"{where}.{name}")

    def set_configs(self, index: int, names: Sequence[str], parsed: Sequence[object]) -> None:
        item = self.item(index)
        keys = self.item_keys(item)
        found = find_key(self.lines, keys, "configs")
        step = self._config_step()
        if found is None:
            if names:
                lines = [f"{' ' * item.column}configs:"]
                lines += [f"{' ' * (item.column + step)}- name: {plain(n)}" for n in names]
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
            self.patch.insert(found.index + 1, [f"{' ' * column}- name: {plain(n)}" for n in names])
            return
        entries, dash = list_items(self.lines, block, f"nodepool[{index}].configs")
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
        self.patch.insert(where, [f"{' ' * dash}- name: {plain(n)}" for n in added])

    def _config_step(self) -> int:
        """How far the file indents a ``configs`` list from its key (production: 0)."""
        nodepool = self.top("nodepool")
        if nodepool is None or nodepool.value:
            return DEFAULT_STEP
        items, _ = list_items(self.lines, self.block(nodepool), "nodepool")
        for item in items:
            found = find_key(self.lines, self.item_keys(item), "configs")
            if found is None or found.value:
                continue
            content = [i for i in self.block(found).children if self.lines[i].is_content]
            if content:
                return self.lines[content[0]].indent - found.column
        return DEFAULT_STEP


def _mirror_lines(value: object) -> list[str]:
    """A list of mirror entries as the shared template writes it; ``[]`` for any other value."""
    if not isinstance(value, list) or not value or not all(isinstance(e, Mapping) for e in value):
        return []
    pad = " " * DEFAULT_STEP
    lines: list[str] = []
    for entry in cast("list[Mapping[str, object]]", value):
        mirrors = entry.get("mirrors")
        lines += [f"{pad}- source: {render_value(entry.get('source'))}", f"{pad}  mirrors:"]
        lines += [
            f"{pad}    - {render_value(m)}"
            for m in (cast("list[object]", mirrors) if isinstance(mirrors, list) else [])
        ]
    return lines


def edit_values(content: str, edits: Sequence[Edit]) -> str:
    """``content`` with ``edits`` made in its text, every other line kept byte for byte.

    Raises ``UneditableFileError`` when the file does not parse, its layout
    is not one the editor handles, or the result would not hold exactly the
    old values with these changes.
    """
    values = values_or_refuse(content)
    lines = split_lines(content)
    editor = _Editor(lines, frozen_from(lines), Patch(lines))
    owners = {
        str(e.key.segments[1]): e.value
        for e in edits
        if isinstance(e, SetValue) and e.key.segments[0] == "owner" and len(e.key.segments) == 2
    }
    if owners:
        editor.set_owners(owners)
    for edit in edits:
        if isinstance(edit, SetConfigs):
            configs = file_pool(values, edit.index).get("configs")
            parsed = cast("list[object]", configs) if isinstance(configs, list) else []
            editor.set_configs(edit.index, edit.names, parsed)
            continue
        segments = edit.key.segments
        if segments[0] == "owner" and len(segments) == 2:
            continue
        if segments == ("platform",):
            editor.set_platform(edit.value)
        elif len(segments) == 1 and segments[0] in MIRROR_FILE_KEYS:
            editor.set_mirrors(str(segments[0]), edit.value)
        elif segments[0] == "nodepool" and len(segments) == 3 and isinstance(segments[1], int):
            editor.set_item_value(segments[1], str(segments[2]), edit.value)
        elif segments[0] == "nodepool" and segments[2:3] == (ANNOTATIONS,) and len(segments) == 4:
            editor.set_annotation(cast("int", segments[1]), str(segments[3]), edit.value)
        else:
            raise UneditableFileError(
                "Wingman does not edit that key", [f"{edit.key} is not a lockable file key"]
            )
    edited = editor.patch.render()
    problems = check_edited(content, edited, expected_values(values, edits))
    if not keeps_comments(lines, editor.patch.deleted, edited):
        problems.append("a comment line would be lost")
    if problems:
        raise UneditableFileError("Wingman could not edit the cluster file safely", problems)
    return edited
