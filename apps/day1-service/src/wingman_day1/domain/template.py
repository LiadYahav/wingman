"""The shared cluster template: what inputs it takes, and rendering it safely.

The specs repo holds one Jinja template (``cluster-template.j2``) that every
spec renders into a hosted-cluster values file. Two things are done with it:

- :func:`analyze_template` walks its syntax tree (it never runs it) and
  lists the inputs it reads, so the web app can build the create form.
- :func:`render_cluster_file` renders it in Jinja's sandbox with
  ``StrictUndefined``: the template is data from a repository, not code
  Wingman trusts, and a missing input is an error, never an empty string.

Inputs are pasted into YAML text, so :func:`check_inputs` refuses values
that could change the document's structure (a newline could add a
``vlanId:`` key; a quote or a backslash could break out of a quoted scalar) before
anything is rendered. :func:`build_inputs` assembles what a render gets: a
spec's preset values, the user's values, and the reserved inputs Wingman
sets itself.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, cast

from jinja2 import StrictUndefined, TemplateError, TemplateSyntaxError, UndefinedError, nodes
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment

from wingman_day1.domain.errors import RenderError

RESERVED_INPUTS: Final = frozenset({"cluster_name", "site", "mce", "openshift_release_version"})
"""Inputs Wingman sets itself; they have dedicated form widgets."""

LEGACY_IDENTITY_ALIASES: Final = frozenset({"site_name", "mce_name"})
"""Older names for ``site`` and ``mce`` the web app still sends; never passed to a render."""

MAX_VALUE_LENGTH: Final = 253
MAX_DEPTH: Final = 6
MAX_LEAVES: Final = 500

# `# Example: x` (a YAML comment, which ends up in the rendered file) or
# `{# Example: x #}` (a Jinja comment, which does not), on a line before the input.
_EXAMPLE = re.compile(r"#\s*[Ee]xample\s*:\s*(.+?)\s*(?:-?#\})?\s*$")
_FIRST_INPUT = re.compile(r"\{\{-?\s*([\w.]+)")
_EXAMPLE_LOOKAHEAD: Final = 4

_JINJA_BUILTINS: Final = frozenset(
    {
        "loop", "range", "namespace", "lipsum", "dict", "true", "false", "none", "True",
        "False", "None", "not", "and", "or", "is", "in", "recursive", "caller", "super",
        "varargs", "kwargs", "joiner",
    }
)  # fmt: skip

_UNSAFE_CATEGORIES: Final = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_YAML_ESCAPES: Final = frozenset('"\\')
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")
_EMPTY: Final[Mapping[str, object]] = MappingProxyType({})


class FieldType(StrEnum):
    """An input's shape.

    Only string, list and object are ever inferred from a template; integer
    and boolean stay because the API has always listed them.
    """

    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    LIST = "list"
    OBJECT = "object"


@dataclass(frozen=True, slots=True)
class TemplateField:
    """One input the template reads, as the create form needs it."""

    name: str
    type: FieldType
    required: bool
    default: object | None = None
    has_default: bool = False
    example: str | None = None
    fields: tuple[TemplateField, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """The API's JSON shape: ``default``, ``fields`` and ``example`` only when present."""
        out: dict[str, object] = {
            "name": self.name,
            "type": str(self.type),
            "required": self.required,
        }
        if self.has_default:
            out["default"] = self.default
        if self.fields:
            out["fields"] = [f.to_dict() for f in self.fields]
        if self.example is not None:
            out["example"] = self.example
        return out


# ── Analysis ────────────────────────────────────────────────────────────────

_NO_DEFAULT: Final = object()
_NON_LITERAL: Final = object()


class _Input:
    """A mutable input descriptor, built while walking the syntax tree."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.required = True
        self.default: object = _NO_DEFAULT
        self.fields: dict[str, _Input] = {}

    def mark_optional(self, default: object) -> None:
        """A ``| default(...)`` was seen; the first literal default wins."""
        self.required = False
        if self.default is _NO_DEFAULT and default not in (_NO_DEFAULT, _NON_LITERAL, None):
            self.default = default

    def field(self, name: str) -> _Input:
        return self.fields.setdefault(name, _Input(name))

    def freeze(self, examples: Mapping[str, str]) -> TemplateField:
        has_default = self.default is not _NO_DEFAULT
        default = self.default if has_default else None
        if self.fields or isinstance(default, list):
            kind = FieldType.LIST
        elif isinstance(default, dict):
            kind = FieldType.OBJECT
        else:
            kind = FieldType.STRING
        return TemplateField(
            name=self.name,
            type=kind,
            required=self.required,
            default=default,
            has_default=has_default,
            example=examples.get(self.name),
            fields=tuple(f.freeze(examples) for f in self.fields.values()),
        )


def _default_of(node: nodes.Filter) -> object:
    """The literal in ``| default(<literal>)``; ``_NON_LITERAL`` for an expression."""
    if node.name != "default" or not node.args:
        return _NO_DEFAULT
    try:
        return node.args[0].as_const()
    except nodes.Impossible:
        return _NON_LITERAL


def _target_names(target: nodes.Node) -> set[str]:
    """The names a ``set`` or ``for`` binds: ``a``, or ``a`` and ``b`` in ``a, b``."""
    if isinstance(target, nodes.Name):
        return {target.name}
    return {n.name for n in target.find_all(nodes.Name)}


def _strip_filters(expr: nodes.Node) -> tuple[nodes.Node | None, bool, object]:
    """``x | f | default(d)`` → ``(x, True, d)``.

    With several defaults the innermost wins, as it does when Jinja renders
    ``x | default(3) | default(4)``. A ``{% filter %}`` block's filter has no
    operand: ``None``.
    """
    optional = False
    default: object = _NO_DEFAULT
    current: nodes.Node | None = expr
    while isinstance(current, nodes.Filter):
        if current.name == "default":
            optional = True
            default = _default_of(current)
        current = current.node
    return current, optional, default


class _Walker:
    """Collects the inputs a template reads. ``loops`` maps a loop variable to its list input."""

    def __init__(self) -> None:
        self.top: dict[str, _Input] = {}
        self.internal: set[str] = set(_JINJA_BUILTINS)

    def _is_input(self, name: str, loops: Mapping[str, _Input], internal: set[str]) -> bool:
        return name not in loops and name not in internal and not name.startswith("_")

    def _top(self, name: str) -> _Input:
        return self.top.setdefault(name, _Input(name))

    def expr(
        self, node: nodes.Node | None, loops: Mapping[str, _Input], internal: set[str]
    ) -> None:
        if node is None:
            return
        if isinstance(node, nodes.Name):
            if self._is_input(node.name, loops, internal):
                self._top(node.name)
        elif isinstance(node, nodes.Getattr):
            inner, optional, default = _strip_filters(node.node)
            if isinstance(inner, nodes.Name) and inner.name in loops:
                child = loops[inner.name].field(node.attr)
                if optional:
                    child.mark_optional(default)
            else:
                self.expr(node.node, loops, internal)
        elif isinstance(node, nodes.Filter):
            self._filter(node, loops, internal)
        elif isinstance(node, nodes.BinExpr):
            self.expr(node.left, loops, internal)
            self.expr(node.right, loops, internal)
        elif isinstance(node, nodes.Concat):
            for child in node.nodes:
                self.expr(child, loops, internal)
        elif isinstance(node, (nodes.List, nodes.Tuple)):
            for item in node.items:
                self.expr(item, loops, internal)
        elif isinstance(node, nodes.Call):
            self.expr(node.node, loops, internal)
            for arg in node.args:
                self.expr(arg, loops, internal)
        elif isinstance(node, nodes.Getitem):
            self.expr(node.node, loops, internal)
        elif isinstance(node, nodes.Compare):
            self.expr(node.expr, loops, internal)
            for operand in node.ops:
                self.expr(operand.expr, loops, internal)
        elif isinstance(node, nodes.CondExpr):
            self.expr(node.test, loops, internal)
            self.expr(node.expr1, loops, internal)
            self.expr(node.expr2, loops, internal)

    def _filter(self, node: nodes.Filter, loops: Mapping[str, _Input], internal: set[str]) -> None:
        inner, optional, default = _strip_filters(node)
        if isinstance(inner, nodes.Name):
            if self._is_input(inner.name, loops, internal):
                found = self._top(inner.name)
                if optional:
                    found.mark_optional(default)
        elif isinstance(inner, nodes.Getattr):
            base, _, _ = _strip_filters(inner.node)
            if isinstance(base, nodes.Name) and base.name in loops:
                child = loops[base.name].field(inner.attr)
                if optional:
                    child.mark_optional(default)
            else:
                self.expr(inner, loops, internal)
        else:
            self.expr(inner, loops, internal)
        for arg in node.args:
            self.expr(arg, loops, internal)

    def body(
        self, body: Iterable[nodes.Node], loops: Mapping[str, _Input], internal: set[str]
    ) -> None:
        for stmt in body:
            if isinstance(stmt, nodes.Output):
                for child in stmt.nodes:
                    self.expr(child, loops, internal)
            elif isinstance(stmt, nodes.Assign):
                # `{% set a = x %}` and `{% set a, b = x, y %}`: the targets are template-local.
                internal.update(_target_names(stmt.target))
                self.expr(stmt.node, loops, internal)
            elif isinstance(stmt, nodes.For):
                self._for(stmt, loops, internal)
            elif isinstance(stmt, nodes.If):
                self.expr(stmt.test, loops, internal)
                self.body(stmt.body, loops, internal)
                self.body(stmt.elif_, loops, internal)
                self.body(stmt.else_, loops, internal)
            elif isinstance(stmt, nodes.Block):
                self.body(stmt.body, loops, internal)
            elif isinstance(stmt, nodes.CallBlock):
                self.expr(stmt.call, loops, internal)
                self.body(stmt.body, loops, internal)
            elif isinstance(stmt, nodes.FilterBlock):
                self.expr(stmt.filter, loops, internal)
                self.body(stmt.body, loops, internal)

    def _for(self, stmt: nodes.For, loops: Mapping[str, _Input], internal: set[str]) -> None:
        if not isinstance(stmt.target, nodes.Name):
            # `for k, v in x.items()`: the targets are loop-local, the iterable is read.
            self.expr(stmt.iter, loops, internal)
            self.body(stmt.body, loops, internal | _target_names(stmt.target))
            return
        loop_var = stmt.target.name
        inside = internal | {loop_var}
        source, optional, default = _strip_filters(stmt.iter)
        list_input: _Input | None = None
        if isinstance(source, nodes.Name) and self._is_input(source.name, loops, internal):
            list_input = self._top(source.name)
        elif isinstance(source, nodes.Getattr):
            base, _, _ = _strip_filters(source.node)
            if isinstance(base, nodes.Name) and base.name in loops:
                list_input = loops[base.name].field(source.attr)
        if list_input is None:
            # `for x in obj.items` or `for i in range(n)`: whatever the iterable reads is an input.
            self.expr(stmt.iter, loops, internal)
            self.body(stmt.body, loops, inside)
            return
        if optional:
            list_input.mark_optional(default)
        self.body(stmt.body, {**loops, loop_var: list_input}, inside)


def _examples(text: str) -> dict[str, str]:
    """``{input name: example}`` from ``# Example:`` comments; the first one per name wins."""
    examples: dict[str, str] = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = _EXAMPLE.search(line)
        if match is None:
            continue
        for following in lines[i + 1 : i + 1 + _EXAMPLE_LOOKAHEAD]:
            used = _FIRST_INPUT.search(following)
            if used:
                name = used.group(1).rsplit(".", 1)[-1]
                if name.isidentifier():
                    examples.setdefault(name, match.group(1).strip())
                break
    return examples


def analyze_template(text: str, *, include_reserved: bool = False) -> list[TemplateField]:
    """The inputs ``text`` reads, in the order it first reads them.

    ``{{ x }}`` is a required string; ``x | default(v)`` makes it optional
    with default ``v`` (``[]`` or ``{}`` make it a list or an object);
    ``{% for item in xs %}`` makes ``xs`` a list whose items have the fields
    the loop reads (``item.field``), nested loops included. The reserved
    inputs and their legacy aliases are left out unless ``include_reserved``.

    Raises:
        RenderError: the template is not valid Jinja.
    """
    try:
        tree = SandboxedEnvironment().parse(text)
    except TemplateSyntaxError as exc:
        raise RenderError(
            "the cluster template is not valid Jinja", [f"line {exc.lineno}: {exc.message}"]
        ) from exc
    walker = _Walker()
    walker.body(tree.body, {}, walker.internal)
    skipped = set() if include_reserved else RESERVED_INPUTS | LEGACY_IDENTITY_ALIASES
    examples = _examples(text)
    return [
        found.freeze(examples)
        for found in walker.top.values()
        if found.name not in walker.internal
        and not found.name.startswith("_")
        and found.name not in skipped
    ]


# ── Rendering ───────────────────────────────────────────────────────────────

_RENDERER: Final = SandboxedEnvironment(
    undefined=StrictUndefined,
    autoescape=False,  # the output is YAML, not HTML; check_inputs guards the values
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_cluster_file(template: str, inputs: Mapping[str, object]) -> str:
    """Render the cluster template in Jinja's sandbox.

    Every input the template reads must be given (``StrictUndefined``).
    Values are not coerced: the legacy renderer turned numeric strings into
    numbers, but the template writes text, so ``"2"`` renders as ``2``
    anyway, and an owner number must stay a string.

    Raises:
        RenderError: a syntax error, a missing input, a sandbox violation,
            a failing expression, or an empty result.
    """
    try:
        compiled = _RENDERER.from_string(template)
    except TemplateSyntaxError as exc:
        raise RenderError(
            "the cluster template is not valid Jinja", [f"line {exc.lineno}: {exc.message}"]
        ) from exc
    try:
        rendered = compiled.render(dict(inputs))
    except SecurityError as exc:
        raise RenderError(
            "the cluster template did something the sandbox forbids", [str(exc)]
        ) from exc
    except UndefinedError as exc:
        raise RenderError("the cluster template reads an undefined input", [str(exc)]) from exc
    except TemplateError as exc:
        raise RenderError("the cluster template failed to render", [str(exc)]) from exc
    except (ArithmeticError, LookupError, TypeError, ValueError) as exc:
        raise RenderError(
            "the cluster template failed to render", [f"{type(exc).__name__}: {exc}"]
        ) from exc
    if not rendered.strip():
        raise RenderError("the cluster template rendered nothing")
    return rendered


# ── Inputs ──────────────────────────────────────────────────────────────────


def _text_problems(path: str, value: str, *, what: str) -> list[str]:
    problems: list[str] = []
    if len(value) > MAX_VALUE_LENGTH:
        problems.append(f"{path}: {what} is longer than {MAX_VALUE_LENGTH} characters")
    unsafe = sorted(
        {c for c in value if unicodedata.category(c) in _UNSAFE_CATEGORIES or c in _YAML_ESCAPES}
    )
    if unsafe:
        shown = ", ".join(f"U+{ord(c):04X}" for c in unsafe)
        problems.append(
            f"{path}: {what} must be one line of plain text without quotes or backslashes "
            f"(found {shown})"
        )
    return problems


class _InputChecker:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.leaves = 0

    def value(self, path: str, value: object, depth: int) -> None:
        if isinstance(value, str):
            self.leaves += 1
            self.problems.extend(_text_problems(path, value, what="a value"))
        elif value is None or isinstance(value, (bool, int, float)):
            self.leaves += 1
        elif isinstance(value, Mapping):
            if self._too_deep(path, depth):
                return
            for key, item in cast("Mapping[object, object]", value).items():
                if not isinstance(key, str) or not _SAFE_KEY.match(key):
                    self.problems.append(
                        f"{path}: key {key!r} must be letters, digits, '_', '.', '/' or '-'"
                    )
                    continue
                self.problems.extend(_text_problems(f"{path}[{key}]", key, what="a key"))
                self.value(f"{path}[{key}]", item, depth + 1)
        elif isinstance(value, (list, tuple)):
            if self._too_deep(path, depth):
                return
            for index, item in enumerate(cast("Sequence[object]", value)):
                self.value(f"{path}[{index}]", item, depth + 1)
        else:
            self.problems.append(f"{path}: a {type(value).__name__} is not a JSON value")

    def _too_deep(self, path: str, depth: int) -> bool:
        if depth > MAX_DEPTH:
            self.problems.append(f"{path}: nested deeper than {MAX_DEPTH} levels")
            return True
        return False


def check_inputs(inputs: Mapping[str, object]) -> list[str]:
    """Why ``inputs`` are unsafe to paste into YAML; empty when they are safe.

    Values are rendered into YAML text, so a newline could add keys such as
    ``vlanId`` and a double quote or a backslash could escape a quoted scalar. Every
    string (value or nested key) must therefore be one line of plain text:
    no control, format, separator or unassigned characters, no quote or
    backslash, at most 253 characters. Top-level names must be Jinja
    identifiers; nested keys may also use ``.``, ``/`` and ``-`` (node label
    keys like ``topology.kubernetes.io/zone``). Only JSON values are allowed,
    at most 6 levels deep and 500 values in all.
    """
    checker = _InputChecker()
    for name, value in inputs.items():
        if not isinstance(name, str) or not name.isidentifier():
            checker.problems.append(f"input name {name!r} is not an identifier")
            continue
        checker.value(name, value, 1)
    if checker.leaves > MAX_LEAVES:
        checker.problems.append(f"{checker.leaves} values given; the limit is {MAX_LEAVES}")
    return checker.problems


def _merge(base: Mapping[str, object], override: Mapping[str, object]) -> dict[str, object]:
    """``override`` over ``base``: mappings merge recursively, lists and scalars replace."""
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _merge(
                cast("Mapping[str, object]", current), cast("Mapping[str, object]", value)
            )
        else:
            merged[key] = value
    return merged


def build_inputs(
    *,
    variables: Mapping[str, object],
    cluster_name: str,
    site: str,
    mce: str,
    openshift_release_version: str | None,
    presets: Mapping[str, object] = _EMPTY,
) -> dict[str, object]:
    """The inputs a render gets: ``presets``, then ``variables``, then the reserved inputs.

    The reserved inputs come from the request, never from ``variables``; the
    web app sends them there too, so a copy that disagrees with the request
    is refused rather than silently replaced. The release version comes
    from the argument, else from the merged values (a spec may preset it).

    Raises:
        RenderError: a reserved input in ``variables`` disagrees with the
            request, or no release version is given.
    """
    expected: dict[str, object] = {
        "cluster_name": cluster_name,
        "site": site,
        "site_name": site,
        "mce": mce,
        "mce_name": mce,
    }
    if openshift_release_version is not None:
        expected["openshift_release_version"] = openshift_release_version
    mismatches = [
        f"{key} is {variables[key]!r} but the request says {want!r}"
        for key, want in expected.items()
        if key in variables and variables[key] != want
    ]
    if mismatches:
        raise RenderError("the inputs disagree with the request", mismatches)
    merged = _merge(presets, variables)
    for alias in LEGACY_IDENTITY_ALIASES:
        merged.pop(alias, None)
    version = openshift_release_version or merged.get("openshift_release_version")
    if not isinstance(version, str) or not version.strip():
        raise RenderError(
            "no OpenShift release version given",
            ["openshift_release_version is required (it becomes the file's mastertag)"],
        )
    merged.update(cluster_name=cluster_name, site=site, mce=mce, openshift_release_version=version)
    return merged
