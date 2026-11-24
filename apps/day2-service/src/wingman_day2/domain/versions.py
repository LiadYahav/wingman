"""OCP versions: where each destination's comes from and how the platform derives it.

The platform keeps what comes before a ``mastertag``'s first ``-``
(``splitList "-" | first`` in argocd-day2-platform's ``inClusterApp.yaml``
and ``operators.yaml``): ``4.16.27-x86_64`` is ``4.16.27``, and so is the
prerelease ``4.16.27-rc.1-x86_64``. The ``operators/<chart>/ocp-versions/``
folders and the ``day2.gitops/ocp-version`` label are keyed by exactly that.

That is not ``wingman_core.domain.release_tags.without_arch``, the release a
tag names, which keeps a prerelease: day2 says what the platform renders. A
tag's shape is core's ``is_release_tag``, as day1 checks it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from wingman_core.domain.release_tags import is_release_tag
from wingman_day2.domain.yaml_values import YamlProblem, parse_yaml

MASTERTAG: Final = "mastertag"


def ocp_version(mastertag: object) -> str:
    """The version the platform derives from a ``mastertag``: what comes before its first ``-``."""
    return str(mastertag).split("-", 1)[0]


def mastertag_problem(mastertag: object) -> str | None:
    """Why ``mastertag`` does not have the shape the version-pin folders assume, if it doesn't."""
    if is_release_tag(str(mastertag)):
        return None
    return (
        f"mastertag {str(mastertag)!r} is not an OpenShift release tag, "
        "<major>.<minor>.<patch>[-<arch>]: the platform's OCP version is what comes before "
        "its first '-'"
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
