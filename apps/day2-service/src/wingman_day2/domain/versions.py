"""OCP versions: where each destination's comes from and how the platform derives it.

The platform strips the arch at the first ``-`` and uses the rest verbatim:
``4.16.27-x86_64`` becomes ``4.16.27``, and ``operators/<chart>/ocp-versions/``
folders are keyed by exactly that full version (``operators.yaml``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from wingman_day2.domain.yaml_values import YamlProblem, parse_yaml

MASTERTAG: Final = "mastertag"
MASTERTAG_PATTERN: Final = re.compile(r"^\d+\.\d+\.\d+(-\S+)?$")
"""render_chain.py's ``MASTERTAG_RE``: ``<major>.<minor>.<patch>[-<arch>]``."""


def ocp_version(mastertag: object) -> str:
    """The version the platform derives from a ``mastertag``."""
    return str(mastertag).split("-", 1)[0]


def mastertag_problem(mastertag: object) -> str | None:
    """Why ``mastertag`` does not have the shape the version-pin folders assume, if it doesn't."""
    if MASTERTAG_PATTERN.match(str(mastertag)):
        return None
    return (
        f"mastertag {str(mastertag)!r} is not <major>.<minor>.<patch>[-<arch>]: the platform "
        "strips the arch at the first '-' and uses the rest verbatim as the OCP version"
    )


@dataclass(frozen=True, slots=True)
class VersionFile:
    """What a version source file says: its ``mastertag``, if any, and what is wrong with it."""

    mastertag: str | None
    problem: str | None = None
    yaml_problem: YamlProblem | None = None
    extra_keys: tuple[str, ...] = ()

    @property
    def ocp_version(self) -> str | None:
        """The derived OCP version, when there is a usable ``mastertag``."""
        return ocp_version(self.mastertag) if self.mastertag else None


def read_version_file(text: str, *, path: str) -> VersionFile:
    """A day1 version source (``version.yaml`` or a hosted-cluster file) or a UPI ``version.yaml``.

    The tag is what Helm would see (the top-level ``mastertag`` key). Keys other
    than ``mastertag`` are recorded: in a UPI ``version.yaml`` each would become
    a chart value, which is a lint error.
    """
    doc, yaml_problem = parse_yaml(text, path=path)
    if yaml_problem is not None:
        return VersionFile(None, yaml_problem.message, yaml_problem=yaml_problem)
    if doc is None:
        return VersionFile(None)
    if not isinstance(doc, dict):
        return VersionFile(None, f"must be a mapping, not a {type(doc).__name__}")
    extra = tuple(sorted(str(key) for key in doc if key != MASTERTAG))
    raw = doc.get(MASTERTAG)
    if raw is None or raw == "":
        return VersionFile(None, "no top-level mastertag", extra_keys=extra)
    return VersionFile(str(raw), mastertag_problem(raw), extra_keys=extra)
