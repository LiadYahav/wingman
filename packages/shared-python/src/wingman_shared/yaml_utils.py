"""YAML utilities using ruamel.yaml for round-trip fidelity.

Key behaviors:
- Multi-document YAML (--- separated) handled natively
- Deep merge: dicts merge recursively, LISTS ARE FULLY REPLACED (Helm semantics)
- Normalize: parse + re-serialize to strip formatting noise before diffing
"""

from __future__ import annotations

import io
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ruamel.yaml import YAML


def _make_yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096  # prevent unwanted line wrapping
    y.indent(sequence=4, offset=2)  # standard YAML list indentation
    y.default_flow_style = False  # always use block style, not inline
    y.allow_duplicate_keys = True  # silently keep last value; avoids crash on real-world Helm files
    return y


@dataclass
class YamlError:
    """Structured YAML parsing error with location info."""
    message: str
    line: int | None = None
    column: int | None = None
    context: str | None = None  # The problematic line
    snippet: str | None = None  # Multi-line snippet with error highlighted

    def __str__(self) -> str:
        loc = ""
        if self.line is not None:
            loc = f" at line {self.line}"
            if self.column is not None:
                loc += f", column {self.column}"
        ctx = f"\n  → {self.context}" if self.context else ""
        return f"{self.message}{loc}{ctx}"

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "context": self.context,
            "snippet": self.snippet,
        }


class YamlParseResult:
    """Result of parsing YAML, includes error info if parsing failed."""

    def __init__(
        self, docs: list[Any], error: YamlError | None = None
    ) -> None:
        self.docs = docs
        self.error = error

    @property
    def ok(self) -> bool:
        return self.error is None

    def __iter__(self):
        return iter(self.docs)

    def __len__(self):
        return len(self.docs)

    def __getitem__(self, idx):
        return self.docs[idx]


def _extract_yaml_error(exc: Exception, content: str) -> YamlError:
    """Extract structured error info from ruamel.yaml exceptions."""
    import re

    error_str = str(exc)
    line: int | None = None
    column: int | None = None
    context: str | None = None
    snippet: str | None = None

    # Try to extract line number from error like "line 3, column 2"
    line_match = re.search(r"line[:\s]+(\d+)", error_str, re.IGNORECASE)
    col_match = re.search(r"column[:\s]+(\d+)", error_str, re.IGNORECASE)

    if line_match:
        line = int(line_match.group(1))
    if col_match:
        column = int(col_match.group(1))

    # Extract snippet with surrounding lines and error indicator
    if line is not None and content:
        lines = content.splitlines()
        if 0 < line <= len(lines):
            context = lines[line - 1]

            # Build snippet with 2 lines before and after
            snippet_lines = []
            start = max(0, line - 3)
            end = min(len(lines), line + 2)

            for i in range(start, end):
                line_num = i + 1
                prefix = ">> " if line_num == line else "   "
                snippet_lines.append(f"{prefix}{line_num:3d} | {lines[i]}")

                # Add error indicator on the error line
                if line_num == line and column is not None:
                    # Create pointer to the column
                    pointer = " " * (len(prefix) + 6 + column - 1) + "^"
                    snippet_lines.append(pointer)

            snippet = "\n".join(snippet_lines)

    # Clean up the error message
    # Remove the "in <unicode string>" parts for cleaner display
    message = re.sub(r'in "[^"]+", ', "", error_str)
    message = re.sub(r"\s+\^.*$", "", message, flags=re.MULTILINE)
    # Remove extra whitespace and newlines
    message = " ".join(message.split())

    return YamlError(
        message=message, line=line, column=column, context=context, snippet=snippet
    )


def parse_multi_document(content: str, *, return_error: bool = False) -> list[Any] | YamlParseResult:
    """Parse a YAML string into a list of dicts.

    Handles both single-document (no ---) and multi-document (--- separated) files.
    ruamel's load_all raises ComposerError on plain YAML files without --- markers,
    so we detect which format is in use and dispatch accordingly.

    Args:
        content: YAML string to parse
        return_error: If True, returns YamlParseResult with error info instead of raising

    Returns:
        List of parsed documents, or YamlParseResult if return_error=True
    """
    try:
        y = _make_yaml()
        stripped = content.strip()
        if not stripped:
            return YamlParseResult([], None) if return_error else []
        if "---" not in stripped:
            # Single document — load_all would raise ComposerError here
            result = y.load(stripped)
            docs = [result] if result is not None else []
            return YamlParseResult(docs, None) if return_error else docs
        docs = [d for d in y.load_all(stripped) if d is not None]
        return YamlParseResult(docs, None) if return_error else docs
    except Exception as exc:
        if return_error:
            error = _extract_yaml_error(exc, content)
            return YamlParseResult([], error)
        # Return empty list for backwards compat, don't crash
        return []


def dump_multi_document(docs: list[Any]) -> str:
    """Serialize a list of dicts to a multi-document YAML string."""
    y = _make_yaml()
    y.explicit_start = True
    stream = io.StringIO()
    y.dump_all(docs, stream)
    return stream.getvalue()


def parse_single(content: str) -> Any:
    """Parse a single-document YAML string. Returns None on invalid YAML."""
    try:
        y = _make_yaml()
        return y.load(content)
    except Exception:
        return None


def dump_single(data: Any) -> str:
    """Serialize a single dict to YAML."""
    y = _make_yaml()
    stream = io.StringIO()
    y.dump(data, stream)
    return stream.getvalue()


def normalize_yaml(content: str) -> str:
    """Parse and re-serialize to canonical form for diffing.

    Strips formatting differences (extra spaces, different quote styles, etc.)
    so that structural diffs are not polluted by formatting noise.
    """
    y = YAML()
    y.default_flow_style = False
    data = y.load(content)
    stream = io.StringIO()
    y.dump(data, stream)
    return stream.getvalue()


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dicts with Helm/YAML list-replacement semantics.

    Rules:
    - Dicts: merged recursively (override keys win)
    - Lists: override FULLY REPLACES base (no append/merge)
    - Scalars: override wins
    - None values in override: removes the key from result

    This matches Helm's values.yaml merge behavior.

    Example:
        base     = {"ports": [80, 443], "image": {"tag": "v1"}}
        override = {"ports": [8080],    "image": {"repo": "myrepo"}}
        result   = {"ports": [8080],    "image": {"tag": "v1", "repo": "myrepo"}}
    """
    result: dict[str, Any] = deepcopy(base)
    for key, value in override.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            # Scalars AND lists: override wins entirely
            result[key] = deepcopy(value)
    return result


def merge_three_layers(
    chart_values: dict[str, Any],
    team_values: dict[str, Any],
    cluster_values: dict[str, Any],
) -> dict[str, Any]:
    """Merge three priority layers: chart < team < cluster.

    Args:
        chart_values: Helm chart's default values.yaml (lowest priority)
        team_values: Team's default values override (middle priority)
        cluster_values: Cluster-specific override (highest priority)

    Returns:
        Final merged values dict
    """
    merged = deep_merge(chart_values, team_values)
    return deep_merge(merged, cluster_values)


def compute_provenance(
    chart_values: dict[str, Any],
    team_values: dict[str, Any],
    cluster_values: dict[str, Any],
) -> dict[str, Any]:
    """Build a provenance map showing which layer each key came from.

    Returns a dict with same structure as merged values, but values are
    "chart" | "team" | "cluster" indicating which layer set the value.
    Used by the frontend merge preview UI.
    """
    merged_ct = deep_merge(chart_values, team_values)
    merged_all = deep_merge(merged_ct, cluster_values)
    return _trace_provenance(merged_all, chart_values, team_values, cluster_values)


def _trace_provenance(
    merged: dict[str, Any],
    chart: dict[str, Any],
    team: dict[str, Any],
    cluster: dict[str, Any],
    path: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in merged.items():
        full_path = f"{path}.{key}" if path else key
        if isinstance(value, dict):
            result[key] = _trace_provenance(
                value,
                chart.get(key, {}) if isinstance(chart.get(key), dict) else {},
                team.get(key, {}) if isinstance(team.get(key), dict) else {},
                cluster.get(key, {}) if isinstance(cluster.get(key), dict) else {},
                full_path,
            )
        else:
            if key in cluster and cluster[key] == value:
                result[key] = "cluster"
            elif key in team and team[key] == value:
                result[key] = "team"
            else:
                result[key] = "chart"
    return result
