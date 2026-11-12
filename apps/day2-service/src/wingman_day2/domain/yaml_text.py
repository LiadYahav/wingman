"""Editing a small YAML mapping file in place: only what changes is rewritten (ADR-0043).

Deploy configs (``<chart>.yaml``) carry comments that matter: why a chart
prunes, why it uses a subchart, why a namespace is shared. A load and dump
would drop them all, so an edit here works on lines, as ADR-0037 does for
cluster files:

- a key whose value is unchanged keeps its lines, byte for byte;
- a changed scalar on one line keeps the line's comment;
- a changed block mapping is edited key by key, recursively;
- any other changed value (a list, a type change) has its block rewritten:
  comment lines at the head of the block are kept, and a comment inside it
  refuses the edit;
- a removed key takes its lines and the comment lines directly above it;
- a new key goes after the last key of its mapping, in the block style
  (sequences indented) the team files use.

Every result is checked before it is returned: it must parse to exactly the
document asked for (types and all), and hold every comment line of the old
text except those of removed keys. Anything else (tabs, several documents,
a layout the editor misreads) is refused with the reason, never written
approximately; a person edits that file by hand.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

import yaml

from wingman_day2.domain.errors import ChangeRefusedError
from wingman_day2.domain.yaml_values import parse_yaml

_KEY = re.compile(r"""^(?P<key>"[^"]*"|'[^']*'|[^\s#'"\-][^:#]*?):(?=\s|$)(?P<rest>.*)$""")
_RULE = "deploy-config-layout"


class _IndentedDumper(yaml.SafeDumper):
    """Block style with sequences indented under their key, as the team files write them."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        """Never indentless: the team files indent their lists."""
        super().increase_indent(flow, False)


def dump_yaml(values: Mapping[str, object]) -> str:
    """A whole file for ``values``: block style, keys in order, sequences indented."""
    if not values:
        return "{}\n"
    return yaml.dump(
        dict(values),
        Dumper=_IndentedDumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=1000,
    )


@dataclass(slots=True)
class _Entry:
    key: str
    line: int
    end: int
    rest: str


def _refuse(path: str, reason: str) -> ChangeRefusedError:
    return ChangeRefusedError(
        f"Wingman cannot edit {path} in place ({reason}); edit it by hand",
        details={"rule": _RULE, "path": path, "reason": reason},
    )


def _is_blank(line: str) -> bool:
    return not line.strip()


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _is_content(line: str) -> bool:
    return not _is_blank(line) and not _is_comment(line)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def same_value(a: object, b: object) -> bool:
    """Equal values of the same types (``True`` is not ``1``, ``"3"`` is not ``3``)."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_value(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_value(x, y) for x, y in zip(a, b, strict=True))
    return a == b


def _scalar(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


class _Editor:
    def __init__(self, lines: list[str], path: str) -> None:
        self.lines = lines
        self.path = path
        self.dropped: list[int] = []

    def entries(self, start: int, end: int, indent: int) -> list[_Entry]:
        found: list[_Entry] = []
        for i in range(start, end):
            line = self.lines[i]
            if not _is_content(line):
                continue
            here = _indent(line)
            if here < indent:
                raise _refuse(self.path, f"line {i + 1} is outside the mapping it should be in")
            if here == indent and not line.lstrip().startswith("-"):
                match = _KEY.match(line.strip())
                if match is None:
                    raise _refuse(self.path, f"line {i + 1} is not a `key: value` line")
                key = match["key"]
                if key[:1] in "\"'":
                    key = key[1:-1]
                found.append(_Entry(key, i, i + 1, match["rest"].strip()))
            elif not found:
                raise _refuse(self.path, f"line {i + 1} belongs to no key")
            else:
                found[-1].end = i + 1
        return found

    def leading(self, start: int, line: int) -> int:
        """The first of the comment lines directly above ``line`` (no blank line between)."""
        first = line
        while first > start and _is_comment(self.lines[first - 1]):
            first -= 1
        return first

    def dump_key(self, key: str, value: object, indent: int) -> list[str]:
        text = dump_yaml({key: value}).rstrip("\n")
        return [f"{' ' * indent}{line}" if line else line for line in text.split("\n")]

    def comment_of(self, entry: _Entry, old: object) -> str | None:
        """The comment on ``entry``'s key line; ``None`` when there is none."""
        rest = entry.rest
        if rest.startswith("#"):
            return rest
        for match in re.finditer(r"\s#", rest):
            head = rest[: match.start()]
            try:
                parsed = yaml.safe_load(f"k: {head}")
            except yaml.YAMLError:
                continue
            if isinstance(parsed, dict) and same_value(parsed.get("k"), old):
                return rest[match.start() :].strip()
        if " #" in rest:
            raise _refuse(
                self.path, f"line {entry.line + 1}: cannot tell its value from its comment"
            )
        return None

    def edit(
        self,
        start: int,
        end: int,
        indent: int,
        old: Mapping[str, object],
        new: Mapping[str, object],
        where: str,
    ) -> list[str]:
        entries = self.entries(start, end, indent)
        if [e.key for e in entries] != list(old):
            raise _refuse(
                self.path, f"the keys of {where or 'the file'} do not read back as written"
            )
        out: list[str] = []
        pos = start
        for entry in entries:
            key = entry.key
            name = f"{where}.{key}" if where else key
            block = range(entry.line + 1, entry.end)
            if key not in new:
                first = self.leading(pos, entry.line)
                out += self.lines[pos:first]
                self.dropped += [i for i in range(first, entry.end) if _is_comment(self.lines[i])]
                pos = entry.end
                continue
            out += self.lines[pos : entry.line]
            before, after = old[key], new[key]
            has_block = any(_is_content(self.lines[i]) for i in block)
            if same_value(before, after):
                out += self.lines[entry.line : entry.end]
            elif (
                isinstance(before, dict)
                and before
                and isinstance(after, dict)
                and has_block
                and (not entry.rest or entry.rest.startswith("#"))
            ):
                child = next(_indent(self.lines[i]) for i in block if _is_content(self.lines[i]))
                out.append(self.lines[entry.line])
                out += self.edit(entry.line + 1, entry.end, child, before, after, name)
            elif _scalar(before) and _scalar(after) and entry.rest and not has_block:
                comment = self.comment_of(entry, before)
                line = self.dump_key(key, after, indent)
                if len(line) != 1:
                    raise _refuse(self.path, f"`{name}`'s new value does not fit on one line")
                out.append(f"{line[0]}  {comment}" if comment else line[0])
                out += self.lines[entry.line + 1 : entry.end]
            else:
                out += self.rewrite(entry, before, after, indent, name)
            pos = entry.end
        out += [
            line for key in new if key not in old for line in self.dump_key(key, new[key], indent)
        ]
        out += self.lines[pos:end]
        return out

    def rewrite(
        self, entry: _Entry, before: object, after: object, indent: int, name: str
    ) -> list[str]:
        """``entry``'s block written anew, keeping the comment lines at its head."""
        block = list(range(entry.line + 1, entry.end))
        head = 0
        while head < len(block) and not _is_content(self.lines[block[head]]):
            head += 1
        inside = [i for i in block[head:] if _is_comment(self.lines[i]) or "#" in self.lines[i]]
        if inside:
            raise _refuse(
                self.path, f"line {inside[0] + 1}: a comment inside `{name}` would be lost"
            )
        comment = self.comment_of(entry, before) if entry.rest else None
        new = self.dump_key(entry.key, after, indent)
        first = f"{new[0]}  {comment}" if comment else new[0]
        return [first, *(self.lines[i] for i in block[:head]), *new[1:]]


def edit_mapping_text(
    text: str,
    new: Mapping[str, object],
    *,
    path: str,
    renames: Mapping[str, str] | None = None,
) -> str:
    """``text``, a YAML mapping, edited in place to hold exactly ``new`` (see the module doc).

    ``renames`` renames top-level keys on their own line first (``repoUrl`` to
    ``repourl``), so the value stays where it was.
    """
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
    editor = _Editor(lines, path)
    for entry in editor.entries(0, len(lines), 0) if old else []:
        target = (renames or {}).get(entry.key)
        if target is None or target in old:
            continue
        line = lines[entry.line]
        lines[entry.line] = line.replace(entry.key, target, 1)
        old = {(target if k == entry.key else k): v for k, v in old.items()}
    if old:
        out = editor.edit(0, len(lines), 0, old, new, "")
    else:
        # An empty file (`{}`, `null`, only comments): keep the comments, write the keys.
        out = [line for line in lines if not _is_content(line)]
        out += [line for key, value in new.items() for line in editor.dump_key(key, value, 0)]
    if not any(_is_content(line) for line in out):
        out.append("{}")
    result = "\n".join(out) + "\n"
    check, problem = parse_yaml(result, path=path)
    got = {str(k): v for k, v in check.items()} if isinstance(check, dict) else {}
    if problem is not None or not same_value(got, {str(k): v for k, v in new.items()}):
        raise _refuse(path, "the edited text does not read back as the intended values")
    expected = [
        lines[i] for i in range(len(lines)) if _is_comment(lines[i]) and i not in editor.dropped
    ]
    if [line for line in out if _is_comment(line)] != expected:
        raise _refuse(path, "the edit would move or drop a comment")
    return result
