"""Tuning profiles from ``tuning/`` in the day1 repo, and the names a nodepool gives (ADR-0061).

A nodepool names node tuning by profile: ``nodepool[].tuningConfig`` in the
cluster file, ``nodepools[i].tuning_config`` as a template input. The day1
CI injects each named manifest into the file's ``tuningConfigmap`` (an
automation key, ADR-0012), resolving a name for cluster ``<c>`` as
``tuning/<c>/<name>.yaml``, else ``tuning/<name>.yaml``. Wingman reads the
same folder and never writes it:

- ``tuning/<name>.yaml`` is a shared profile: one YAML document, a ``Tuned``
  (``tuned.openshift.io/v1``) or a ``PerformanceProfile``
  (``performance.openshift.io/v2``), whose ``metadata.name`` is ``<name>``,
  a DNS-1123 label of at most 63 characters;
- ``tuning/<cluster>/<name>.yaml`` is that cluster's variant, by the same
  rules;
- nothing deeper. Any other file is a problem and is never offered;
  documentation (``*.md``) and dot files are skipped.

A nodepool takes at most one PerformanceProfile (a HyperShift NodePool
references at most one) and any number of Tuned. A Tuned whose data
includes ``openshift-node-performance-<pp>`` builds on the profile that
PerformanceProfile ``<pp>`` generates: the catalogue says so, and the web
warns about a pool that has the Tuned without it (never a 422).

Names are written as the user decided: a string for one, a list for
several, no key for none. Flavors and creates name shared profiles; an edit
of an existing cluster may also add a variant of its own or a name its
``tuningConfigmap`` already holds.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, cast

import yaml

from wingman_core.domain.git import RepoPath
from wingman_day1.domain.cluster_file import load_values
from wingman_day1.domain.errors import InvalidClusterFileError

TUNING_DIR: Final = RepoPath("tuning")
TUNING_INPUT: Final = "tuning_config"
"""A nodepool's template input."""
TUNING_FILE_KEY: Final = "tuningConfig"
"""A nodepool's key in the cluster file."""
TUNING_CONFIGMAP: Final = "tuningConfigmap"
"""The CI's top-level key holding the injected manifests (an automation key)."""
MAX_PROFILE_NAME: Final = 63
MAX_PROFILES_PER_NODEPOOL: Final = 16
MAX_TUNING_FILES: Final = 500
"""Files read from ``tuning/`` at most; more is a problem, and the rest are not read."""

PERFORMANCE_INCLUDE: Final = "openshift-node-performance-"
"""The prefix of the Tuned profile a PerformanceProfile generates (``...-<ppName>``)."""
_SUFFIX: Final = ".yaml"
_DNS_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_SHOWN: Final = 120


class TuningKind(StrEnum):
    """The two manifest kinds the Node Tuning Operator reads."""

    TUNED = "Tuned"
    PERFORMANCE_PROFILE = "PerformanceProfile"


_API_VERSIONS: Final = {
    TuningKind.TUNED: "tuned.openshift.io/v1",
    TuningKind.PERFORMANCE_PROFILE: "performance.openshift.io/v2",
}


@dataclass(frozen=True, slots=True)
class TuningProfile:
    """One profile file: a shared one, or a cluster's variant."""

    name: str
    kind: TuningKind
    summary: str | None
    """A Tuned's ``[main]`` ``summary=``, from its first profile entry."""
    path: RepoPath
    requires_performance_profile: str | None = None
    """A Tuned that includes ``openshift-node-performance-<pp>``: the ``<pp>`` it builds on."""


@dataclass(frozen=True, slots=True)
class TuningProblem:
    """A file under ``tuning/`` that is not offered, and why."""

    path: str
    detail: str


@dataclass(frozen=True, slots=True)
class TuningCatalog:
    """What ``tuning/`` offers: shared profiles, per-cluster variants, and the files that fail."""

    found: bool = True
    """``False``: the day1 repo has no ``tuning/``; nothing resolves."""
    shared: Mapping[str, TuningProfile] = field(default_factory=dict)
    variants: Mapping[str, Mapping[str, TuningProfile]] = field(default_factory=dict)
    """By cluster name, then profile name."""
    problems: tuple[TuningProblem, ...] = ()

    @classmethod
    def from_files(cls, files: Mapping[str, str], *, listed: int | None = None) -> TuningCatalog:
        """The catalogue from ``{path: content}`` of the files under ``tuning/`` worth reading.

        ``listed`` is how many such files the folder holds, when more than
        :data:`MAX_TUNING_FILES` were left unread.
        """
        shared: dict[str, TuningProfile] = {}
        variants: dict[str, dict[str, TuningProfile]] = {}
        problems: list[TuningProblem] = []
        for path in sorted(files)[:MAX_TUNING_FILES]:
            parts = path.split("/")[1:]
            if is_documentation(path):
                continue
            profile = _profile(path, parts, files[path])
            if isinstance(profile, str):
                problems.append(TuningProblem(path, profile))
            elif len(parts) == 1:
                shared[profile.name] = profile
            else:
                variants.setdefault(parts[0], {})[profile.name] = profile
        total = max(len(files), listed or 0)
        if total > MAX_TUNING_FILES:
            problems.append(
                TuningProblem(
                    str(TUNING_DIR), f"{total} files; only the first {MAX_TUNING_FILES} are read"
                )
            )
        return cls(True, shared, variants, tuple(problems))

    def profiles(self) -> list[TuningProfile]:
        """The shared profiles, by name."""
        return [self.shared[name] for name in sorted(self.shared)]

    def clusters_with_variant(self, name: str) -> list[str]:
        """The clusters with their own ``tuning/<cluster>/<name>.yaml``."""
        return sorted(cluster for cluster, found in self.variants.items() if name in found)

    def unknown_name(self, where: str, name: str) -> str:
        """Why ``name`` is not a shared profile, with a "did you mean" for a near miss."""
        clusters = self.clusters_with_variant(name)
        if clusters:
            return (
                f"{where}: {name} is a variant for cluster {', '.join(clusters)} only; a flavor "
                f"or a new cluster names shared profiles from {TUNING_DIR}/"
            )
        close = difflib.get_close_matches(name, list(self.shared), n=1, cutoff=0.8)
        hint = f" (did you mean {close[0]}?)" if close else ""
        if not self.found:
            hint = f"; the day1 repo has no {TUNING_DIR}/ folder"
        return f"{where}: {name} is not a tuning profile in {TUNING_DIR}/{hint}"


def is_documentation(path: str) -> bool:
    """``*.md`` and dot files under ``tuning/``: not profiles, and not problems either."""
    parts = path.split("/")[1:]
    return any(p.startswith(".") for p in parts) or path.endswith(".md")


def _profile(path: str, parts: Sequence[str], content: str) -> TuningProfile | str:
    """The profile in one file, or why it is not one."""
    if len(parts) > 2:
        return f"{TUNING_DIR}/ holds profiles and one folder per cluster, nothing deeper"
    if not parts[-1].endswith(_SUFFIX):
        return f"not a {_SUFFIX} file"
    name = parts[-1].removesuffix(_SUFFIX)
    problem = name_problem(name)
    if problem is not None:
        return f"the file name {problem}"
    document = _document(content)
    if isinstance(document, str):
        return document
    kind = _kind(document)
    if not isinstance(kind, TuningKind):
        return kind
    metadata = document.get("metadata")
    found = (
        cast("Mapping[str, object]", metadata).get("name") if isinstance(metadata, dict) else None
    )
    if found != name:
        return f"metadata.name is {found}; it must be the file's name, {name}"
    if kind is not TuningKind.TUNED:
        return TuningProfile(name, kind, None, RepoPath(path))
    data = _profile_data(document)
    summary = _main_values(data[0], "summary")[:1] if data else []
    requires = [
        value.removeprefix(PERFORMANCE_INCLUDE)
        for text in data
        for line in _main_values(text, "include")
        for value in (v.strip() for v in line.split(","))
        if value.startswith(PERFORMANCE_INCLUDE) and value != PERFORMANCE_INCLUDE
    ]
    return TuningProfile(
        name, kind, summary[0] if summary else None, RepoPath(path), next(iter(requires), None)
    )


def _document(content: str) -> Mapping[str, object] | str:
    """The file's one YAML mapping, or why it has none."""
    try:
        documents = [d for d in yaml.safe_load_all(content) if d is not None]
    except yaml.YAMLError as exc:
        return f"not valid YAML: {str(exc).splitlines()[0]}"
    if len(documents) != 1 or not isinstance(documents[0], dict):
        return (
            "must be exactly one YAML mapping, a Tuned or a PerformanceProfile; found "
            f"{len(documents)} documents"
        )
    return cast("Mapping[str, object]", documents[0])


def _kind(document: Mapping[str, object]) -> TuningKind | str:
    """The manifest's kind, or why it is neither a Tuned nor a PerformanceProfile."""
    pair = (document.get("apiVersion"), document.get("kind"))
    for kind, api in _API_VERSIONS.items():
        if pair == (api, kind.value):
            return kind
    wanted = " or ".join(f"{k.value} ({api})" for k, api in _API_VERSIONS.items())
    return f"apiVersion {pair[0]!r} kind {pair[1]!r}; it must be {wanted}"


def _profile_data(document: Mapping[str, object]) -> list[str]:
    """The ``data`` text of each of a Tuned's ``spec.profile`` entries, in order."""
    spec = document.get("spec")
    profiles = cast("Mapping[str, object]", spec).get("profile") if isinstance(spec, dict) else None
    if not isinstance(profiles, list):
        return []
    entries = [cast("Mapping[str, object]", p) for p in profiles if isinstance(p, dict)]
    return [str(p["data"]) for p in entries if isinstance(p.get("data"), str)]


def _main_values(data: str, key: str) -> list[str]:
    """The non-empty values of ``key=`` in the ``[main]`` section of a Tuned profile's ini text."""
    section = ""
    found: list[str] = []
    for line in data.splitlines():
        text = line.strip()
        if text.startswith("[") and text.endswith("]"):
            section = text[1:-1].strip()
        elif section == "main" and "=" in text:
            name, value = text.split("=", 1)
            if name.strip() == key and value.strip():
                found.append(value.strip())
    return found


def name_problem(name: str) -> str | None:
    """Why ``name`` cannot be a profile name (a DNS-1123 label of at most 63 characters)."""
    if len(name) > MAX_PROFILE_NAME:
        return f"{name[:20]}... is longer than {MAX_PROFILE_NAME} characters"
    if not _DNS_LABEL.match(name):
        return f"{name!r} is not a DNS-1123 label (lowercase letters, digits and '-')"
    return None


# ── Names as a nodepool gives them ───────────────────────────────────────────


def tuning_names(value: object) -> list[str] | None:
    """The names a ``tuning_config`` or ``tuningConfig`` value gives; ``None`` for another shape.

    A string is one name; a list of strings, several in order; ``None``,
    ``""`` and ``[]`` are none.
    """
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        items = cast("Sequence[object]", value)
        if all(isinstance(item, str) and item for item in items):
            return [str(item) for item in items]
    return None


def file_value(names: Sequence[str]) -> str | list[str]:
    """How the file writes ``names`` (at least one): a string for one, a list for several."""
    return names[0] if len(names) == 1 else list(names)


def show_names(names: Sequence[str]) -> str:
    """``names`` as a problem shows them: a JSON-like list, cut short."""
    text = "[" + ", ".join(f'"{n}"' for n in names) + "]"
    return text if len(text) <= _SHOWN else f"{text[: _SHOWN - 4]}...]"


def nodepool_entries(
    values: Mapping[str, object], key: str
) -> list[tuple[int, Mapping[str, object]]]:
    """The mappings of the list at ``key`` (``nodepools`` or ``nodepool``), with their positions."""
    pools = values.get(key)
    if not isinstance(pools, (list, tuple)):
        return []
    return [
        (index, cast("Mapping[str, object]", pool))
        for index, pool in enumerate(cast("Sequence[object]", pools))
        if isinstance(pool, Mapping)
    ]


def input_problems(inputs: Mapping[str, object], catalog: TuningCatalog) -> list[str]:
    """Why the nodepools' ``tuning_config`` inputs break the rule (flavor save and create).

    Each name must be a shared profile, given once, at most 16 per nodepool.
    """
    problems: list[str] = []
    for index, pool in nodepool_entries(inputs, "nodepools"):
        if TUNING_INPUT not in pool:
            continue
        where = f"nodepools[{index}].{TUNING_INPUT}"
        names = tuning_names(pool[TUNING_INPUT])
        if names is None:
            problems.append(f"{where}: must be a list of tuning profile names")
            continue
        if len(names) > MAX_PROFILES_PER_NODEPOOL:
            problems.append(
                f"{where}: {len(names)} profiles; the limit is {MAX_PROFILES_PER_NODEPOOL}"
            )
        seen: set[str] = set()
        for position, name in enumerate(names):
            at = f"{where}[{position}]"
            if name in seen:
                problems.append(f"{at}: {name} is listed twice")
            elif name not in catalog.shared:
                problems.append(catalog.unknown_name(at, name))
            seen.add(name)
        kinds = {n: p.kind for n, p in catalog.shared.items()}
        problems += performance_problems(where, names, kinds)
    return problems


def performance_problems(
    where: str, names: Sequence[str], kinds: Mapping[str, TuningKind]
) -> list[str]:
    """A nodepool that names more than one PerformanceProfile (HyperShift allows one)."""
    found = [n for n in dict.fromkeys(names) if kinds.get(n) is TuningKind.PERFORMANCE_PROFILE]
    if len(found) < 2:
        return []
    return [
        f"{where}: at most one PerformanceProfile per nodepool (HyperShift); it names "
        f"{', '.join(found)}"
    ]


def configmap_names(values: Mapping[str, object]) -> set[str]:
    """The names the file's ``tuningConfigmap`` holds (``- name: <name>`` entries)."""
    entries = values.get(TUNING_CONFIGMAP)
    if not isinstance(entries, list):
        return set()
    return {
        str(cast("Mapping[str, object]", e)["name"])
        for e in cast("Sequence[object]", entries)
        if isinstance(e, dict) and "name" in e
    }


def file_names(values: Mapping[str, object]) -> list[str]:
    """Every name the file's nodepools give, first-seen order, each once (the CI's reading)."""
    found: dict[str, None] = {}
    for _, pool in nodepool_entries(values, "nodepool"):
        for name in tuning_names(pool.get(TUNING_FILE_KEY)) or []:
            found.setdefault(name)
    return list(found)


def edit_problems(
    old: Mapping[str, object],
    new: Mapping[str, object],
    catalog: TuningCatalog,
    *,
    cluster_name: str,
) -> list[str]:
    """Why an edit's ``tuningConfig`` names may not be proposed (ADR-0061).

    Only names the edit adds to the file are checked: each must be a shared
    profile, a variant for ``cluster_name`` (the chart's), or an entry of
    the file's ``tuningConfigmap``. A value of another shape is refused
    unless the file had it already.
    """
    had = set(file_names(old))
    old_values = [pool.get(TUNING_FILE_KEY) for _, pool in nodepool_entries(old, "nodepool")]
    kinds = _kinds(old, catalog, cluster_name)
    allowed = {*kinds, *configmap_names(old)}
    problems: list[str] = []
    for index, pool in nodepool_entries(new, "nodepool"):
        where = f"nodepool[{index}].{TUNING_FILE_KEY}"
        raw = pool.get(TUNING_FILE_KEY)
        names = tuning_names(raw)
        if names is None:
            if raw not in old_values:
                problems.append(f"{where}: must be a tuning profile name or a list of names")
            continue
        problems += [
            f"{where}: {name} is not in {TUNING_DIR}/, in {TUNING_DIR}/{cluster_name}/ or in this "
            f"file's {TUNING_CONFIGMAP}"
            for name in dict.fromkeys(names)
            if name not in had and name not in allowed
        ]
        if raw not in old_values:
            problems += performance_problems(where, names, kinds)
    return problems


def _kinds(
    values: Mapping[str, object], catalog: TuningCatalog, cluster_name: str
) -> dict[str, TuningKind]:
    """Each name's kind for one cluster: its ``tuningConfigmap``, the shared file, its variant.

    Later sources win, as the CI resolves a name (a variant over the shared
    file); a hand-written entry counts for a name the catalogue lacks.
    """
    kinds: dict[str, TuningKind] = {}
    entries = values.get(TUNING_CONFIGMAP)
    for entry in cast("Sequence[object]", entries) if isinstance(entries, list) else []:
        found = cast("Mapping[str, object]", entry) if isinstance(entry, dict) else {}
        document = _document(str(found.get("tuning", "")))
        kind = _kind(document) if not isinstance(document, str) else None
        if "name" in found and isinstance(kind, TuningKind):
            kinds[str(found["name"])] = kind
    kinds.update({n: p.kind for n, p in catalog.shared.items()})
    kinds.update({n: p.kind for n, p in catalog.variants.get(cluster_name, {}).items()})
    return kinds


def edit_text_problems(
    current: str, edited: str, catalog: TuningCatalog, *, cluster_name: str
) -> list[str]:
    """:func:`edit_problems` for two file texts; a text that does not parse is left to others."""
    try:
        new = load_values(edited)
    except InvalidClusterFileError:
        return []
    try:
        old = load_values(current)
    except InvalidClusterFileError:
        old = {}
    return edit_problems(old, new, catalog, cluster_name=cluster_name)
