"""``defaults/<scope>/exclusions.yaml``: the one structural opt-out from a fleet default.

``exclusions: {<chart>: [<MCE or cluster name>, ...]}``. The operators chart
turns it into ``exclude:`` entries of the defaults generator. The template is
strict about types (a non-map ``exclusions`` or a non-list entry makes it
``fail``, so no app of that scope renders for the team) and silent about
names (a typo excludes nothing); ``lints.lint_exclusions`` catches both.

The file explains itself in comments (the platform's own example is mostly
comments), so Wingman edits it in place (ADR-0053): :func:`set_excluded`
changes one chart's list line by line and keeps every comment line byte for
byte, or refuses with the reason.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

import yaml

from wingman_day2.domain.errors import ChangeRefusedError
from wingman_day2.domain.yaml_text import (
    MappingEntry,
    dump_yaml,
    indent_of,
    is_comment,
    is_content,
    mapping_entries,
    refuse_edit,
    same_value,
)
from wingman_day2.domain.yaml_values import parse_yaml

EXCLUSIONS_KEY: Final = "exclusions"
LAYOUT_RULE: Final = "exclusions-layout"
"""The refusal rule of an exclusions file Wingman cannot edit exactly."""

_PLAIN: Final = re.compile(r"^[A-Za-z0-9]([-A-Za-z0-9._]*[A-Za-z0-9])?$")
_EMPTY: Final = ("", "{}", "[]", "null", "~")


@dataclass(frozen=True, slots=True)
class Exclusions:
    """Which names each fleet-default chart is excluded from."""

    by_chart: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def excluded_charts(self, name: str) -> frozenset[str]:
        """The charts whose list names ``name``."""
        return frozenset(chart for chart, names in self.by_chart.items() if name in names)

    def names(self, chart: str) -> tuple[str, ...]:
        """The names ``chart``'s entry lists."""
        return self.by_chart.get(chart, ())


def platform_exclusions(doc: object) -> Exclusions | None:
    """What the operators chart makes of an exclusions file; ``None`` where its render fails.

    ``doc`` is the parsed file (``None`` when absent or empty). A file Helm
    cannot load as values (not a mapping) fails the render too. Only
    ``exclusions`` is read, as ``.Values.exclusions | default dict``.
    """
    if doc is not None and not isinstance(doc, Mapping):
        return None
    raw = doc.get(EXCLUSIONS_KEY) if isinstance(doc, Mapping) else None
    if not raw:
        return Exclusions()
    if not isinstance(raw, Mapping):
        return None
    by_chart: dict[str, tuple[str, ...]] = {}
    for chart, names in raw.items():
        if not names:
            continue
        if not isinstance(names, list):
            return None
        by_chart[str(chart)] = tuple(str(n) for n in names)
    return Exclusions(by_chart)


# ── editing in place ────────────────────────────────────────────────────────


def _refuse(path: str, reason: str) -> ChangeRefusedError:
    return refuse_edit(path, reason, LAYOUT_RULE)


def _name(name: str) -> str:
    return name if _PLAIN.match(name) else yaml.safe_dump(name).strip().removesuffix("\n...")


def _item(line: str, path: str, number: int) -> str:
    """The name a ``- <name>`` line lists."""
    try:
        parsed = yaml.safe_load(line.strip())
    except yaml.YAMLError:
        parsed = None
    if not (isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], str)):
        raise _refuse(path, f"line {number} is not a `- <name>` line")
    return parsed[0]


def _comment(rest: str) -> str:
    """The ``# ...`` part of what follows a key, with the two spaces before it; else ``""``."""
    at = rest.find("#")
    return f"  {rest[at:]}" if at >= 0 else ""


def _value(rest: str) -> str:
    """What follows a key, without its comment."""
    if rest.startswith("#"):
        return ""
    return rest.split(" #", 1)[0].strip()


def _chart_block(chart: str, names: Sequence[str], indent: int, item_indent: int) -> list[str]:
    head = dump_yaml({chart: list(names)}).rstrip("\n").split("\n")
    return [f"{' ' * indent}{head[0]}", *(f"{' ' * item_indent}- {_name(n)}" for n in names)]


@dataclass(slots=True)
class _ChartList:
    """One chart's entry: its key, whether it is a flow list, and its item lines."""

    entry: MappingEntry
    flow: bool
    items: list[tuple[int, str]]

    @classmethod
    def read(cls, lines: list[str], entry: MappingEntry, path: str) -> _ChartList:
        value = _value(entry.rest)
        following = [i for i in range(entry.line + 1, entry.end) if is_content(lines[i])]
        if value:
            try:
                parsed = [] if value in _EMPTY else yaml.safe_load(value)
            except yaml.YAMLError:
                parsed = None
            if not (isinstance(parsed, list) and all(isinstance(n, str) for n in parsed)):
                raise _refuse(path, f"line {entry.line + 1}: `{entry.key}` is not a list of names")
            if following:
                raise _refuse(path, f"line {entry.line + 1}: `{entry.key}` goes on past its line")
            return cls(entry, True, [(entry.line, n) for n in parsed])
        items = []
        for i in following:
            if not lines[i].lstrip().startswith("- "):
                raise _refuse(path, f"line {i + 1}: `{entry.key}` holds more than names")
            items.append((i, _item(lines[i], path, i + 1)))
        return cls(entry, False, items)

    @property
    def names(self) -> list[str]:
        return [n for _, n in self.items]


def set_excluded(text: str | None, chart: str, names: Sequence[str], *, path: str) -> str | None:
    """``text`` (an exclusions file, ``None`` if absent) with ``chart`` excluding just ``names``.

    Names already listed keep their line and their place; new ones go after
    the last one; a chart left with no name loses its key line (its comment
    lines stay); an ``exclusions`` left with no chart reads
    ``exclusions: {}``. An absent file that stays absent comes back as
    ``None``. The result must parse to the same document with only that list
    changed, and keep every comment line in order, else the edit is refused
    (``exclusions-layout``): a person edits that file by hand.
    """
    wanted = list(dict.fromkeys(names))
    if text is None or not text.strip():
        return dump_yaml({EXCLUSIONS_KEY: {chart: wanted}}) if wanted else text
    if "\t" in text:
        raise _refuse(path, "it is indented with tabs")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if any(line.strip() in ("---", "...") for line in lines):
        raise _refuse(path, "it has a YAML document marker")
    doc, problem = parse_yaml(text, path=path)
    if problem is not None:
        raise _refuse(path, problem.message)
    if doc is not None and not isinstance(doc, dict):
        raise _refuse(path, "it is not a mapping")
    old = {str(k): v for k, v in (doc or {}).items()}
    current = old.get(EXCLUSIONS_KEY)
    if current is not None and not isinstance(current, dict):
        raise _refuse(path, f"`{EXCLUSIONS_KEY}` is not a mapping of charts")
    out = _edit(lines, chart, wanted, path=path, has_keys=bool(old))
    entries = dict(current or {})
    listed = entries.get(chart) or []
    final = [n for n in listed if n in wanted] + [n for n in wanted if n not in listed]
    if final:
        entries[chart] = final
    else:
        entries.pop(chart, None)
    expected = dict(old)
    if EXCLUSIONS_KEY in old or final:
        expected[EXCLUSIONS_KEY] = entries
    result = "\n".join(out) + "\n"
    check, problem = parse_yaml(result, path=path)
    got = {str(k): v for k, v in check.items()} if isinstance(check, dict) else {}
    if EXCLUSIONS_KEY in got and got[EXCLUSIONS_KEY] is None:
        got[EXCLUSIONS_KEY] = {}
    if EXCLUSIONS_KEY in expected and not expected[EXCLUSIONS_KEY]:
        got.setdefault(EXCLUSIONS_KEY, {})
    if problem is not None or not same_value(got, expected):
        raise _refuse(path, "the edited text does not read back as the intended exclusions")
    if [x for x in out if is_comment(x)] != [x for x in lines if is_comment(x)]:
        raise _refuse(path, "the edit would move or drop a comment")
    return result


def _edit(
    lines: list[str], chart: str, wanted: list[str], *, path: str, has_keys: bool
) -> list[str]:
    top = mapping_entries(lines, 0, len(lines), 0, path=path, rule=LAYOUT_RULE) if has_keys else []
    block = next((e for e in top if e.key == EXCLUSIONS_KEY), None)
    if block is None:
        if not wanted:
            return lines
        out = [x for x in lines if not (is_content(x) and x.strip() == "{}")]
        return [*out, f"{EXCLUSIONS_KEY}:", *_chart_block(chart, wanted, 2, 4)]
    value = _value(block.rest)
    children = [i for i in range(block.line + 1, block.end) if is_content(lines[i])]
    if value or not children:
        if value not in _EMPTY or children:
            raise _refuse(path, f"line {block.line + 1}: `{EXCLUSIONS_KEY}` is in flow style")
        if not wanted:
            return lines
        head = f"{EXCLUSIONS_KEY}:{_comment(block.rest)}"
        return [
            *lines[: block.line],
            head,
            *_chart_block(chart, wanted, 2, 4),
            *lines[block.line + 1 :],
        ]
    indent = indent_of(lines[children[0]])
    charts = mapping_entries(lines, block.line + 1, block.end, indent, path=path, rule=LAYOUT_RULE)
    lists = {e.key: _ChartList.read(lines, e, path) for e in charts}
    item_indent = next(
        (indent_of(lines[i]) for c in lists.values() if not c.flow for i, _ in c.items),
        indent + 2,
    )
    found = lists.get(chart)
    if found is None:
        if not wanted:
            return lines
        new = _chart_block(chart, wanted, indent, item_indent)
        return [*lines[: block.end], *new, *lines[block.end :]]
    entry = found.entry
    keep = [n for n in found.names if n in wanted]
    add = [n for n in wanted if n not in found.names]
    if not keep and not add:
        out = [
            *lines[: entry.line],
            *(x for x in lines[entry.line + 1 : entry.end] if is_comment(x)),
            *lines[entry.end :],
        ]
        if len(charts) == 1:
            out[block.line] = f"{EXCLUSIONS_KEY}: {{}}{_comment(block.rest)}"
        return out
    if found.flow:
        key = lines[entry.line].strip().split(":", 1)[0]
        tail = entry.rest[entry.rest.find("]") + 1 :] if "]" in entry.rest else entry.rest
        flow = "[" + ", ".join(_name(n) for n in [*keep, *add]) + "]"
        head = f"{' ' * indent}{key}: {flow}{_comment(tail)}"
        return [*lines[: entry.line], head, *lines[entry.line + 1 :]]
    dropped = {i for i, n in found.items if n not in wanted}
    at = indent_of(lines[found.items[0][0]]) if found.items else item_indent
    last = max((i for i, _ in found.items), default=entry.line)
    out = []
    for i, line in enumerate(lines):
        if i not in dropped:
            out.append(line)
        if i == last:
            out += [f"{' ' * at}- {_name(n)}" for n in add]
    return out
