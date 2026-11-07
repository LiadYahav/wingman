"""Reading and writing Helm value files.

Helm reads YAML through a JSON conversion, so a timestamp-looking scalar stays
a string; the loader here does the same, which also keeps every parsed value
JSON-serialisable for the API. A file that does not parse is reported, never
silently treated as empty (ADR-0004: no swallowed read errors).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import yaml

_TIMESTAMP = "tag:yaml.org,2002:timestamp"


class _HelmLoader(yaml.SafeLoader):
    """SafeLoader without the timestamp resolver."""


_HelmLoader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag != _TIMESTAMP]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


@dataclass(frozen=True, slots=True)
class YamlProblem:
    """Why a file could not be used, with the position when the parser gave one."""

    path: str
    message: str
    line: int | None = None
    column: int | None = None


def parse_yaml(text: str, *, path: str) -> tuple[object, YamlProblem | None]:
    """The single document in ``text`` (``None`` when empty), or the parse problem."""
    try:
        return yaml.load(text, Loader=_HelmLoader), None  # noqa: S506 - a SafeLoader subclass
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        problem = str(getattr(exc, "problem", None) or exc)
        return None, YamlProblem(
            path,
            f"not valid YAML: {problem}",
            line=mark.line + 1 if mark is not None else None,
            column=mark.column + 1 if mark is not None else None,
        )


def parse_values(text: str, *, path: str) -> tuple[dict[str, object], YamlProblem | None]:
    """A values file as a mapping: empty is ``{}``, anything but a mapping is a problem."""
    doc, problem = parse_yaml(text, path=path)
    if problem is not None:
        return {}, problem
    if doc is None:
        return {}, None
    if not isinstance(doc, dict):
        return {}, YamlProblem(path, f"must be a mapping of values, not a {type(doc).__name__}")
    return {str(key): value for key, value in doc.items()}, None


def dump_values(values: Mapping[str, object]) -> str:
    """YAML for a values or deploy-config file Wingman writes (``{}`` when empty)."""
    if not values:
        return "{}\n"
    return yaml.safe_dump(
        dict(values), sort_keys=False, default_flow_style=False, allow_unicode=True
    )
