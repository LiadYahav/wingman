"""Machine configs: the names a nodepool's ``configs`` may use, by the day1 CI's rule (ADR-0027).

A nodepool lists MachineConfig sources by name (``configs: [{name: ...}]``).
After the merge request is pushed, the day1 CI resolves each name to a file
under ``mc-files/`` in the day1 repo, renders it and writes the result into
the file's ``mcConfigMap``. A name that resolves nowhere fails that
pipeline, after the MR is open. Wingman applies the same rule first, so a
typo is a 422 on the form instead.

How the CI resolves a name, described here in Wingman's words:

1. **A network template comes first.** Each
   ``mc-files/templates/nm-conf-template-<hw>.bu`` is one hardware type
   ``<hw>``. A name that ends in ``-<hw>`` is rendered from that template
   for the cluster whose file lists it. When several types match, the
   longest wins: ``nm-conf-x-dell-data`` is ``dell-data``, not ``dell``.
   The name ``nm-conf`` itself is rendered from the generic template
   ``mc-files/templates/nm-conf-template.bu``, for any hardware (ADR-0027's
   2026-11-12 amendment). Templates are tried before static files, so a
   static file whose name ends in ``-<hw>`` is never the one used.
2. **Otherwise it is a static file.** A ``<name>.bu`` anywhere wins over a
   file named exactly ``<name>``; within each, the ``mc-files/`` root wins
   over subfolders, and subfolders are taken in path order. ``templates/``
   is never a static source.
3. **A butane file's config name has no ``.bu``.** The CI renders ``x.bu``
   as the config ``x``, and the name ``x.bu`` is never found. Any other
   file's config name is its whole file name.

Wingman narrows the rule in two ways. ``legacy/`` holds restored originals
of clusters not yet onboarded: the CI would find a name there, but Wingman
neither offers nor accepts one for a new flavor or cluster. Documentation
(``*.md``, dot files) is not a config.

A nodepool entry is ``{name: <static config>}`` or ``{name: nm-conf,
hardware: <hw>}``. The second is the cluster's own network config:
:func:`expand_network_configs` turns it into ``{name:
nm-conf-<clusterName>-<hw>}`` before the shared template renders, so the
template and the file the CI reads keep the shape they have. The hardware
``generic`` (reserved) stands for the generic template and is written as
plain ``{name: nm-conf}``. An entry without hardware is not the generic one:
in a flavor's rule and the nodepool defaults it means "the nodepool picks".
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from wingman_core.domain.git import RepoPath
from wingman_day1.domain.errors import InvalidNodepoolDefaultsError
from wingman_day1.domain.paths import MC_FILES

NETWORK_CONFIG: Final = "nm-conf"
"""The entry name that stands for the cluster's own network config."""
TEMPLATES_DIR: Final = "templates"
LEGACY_DIR: Final = "legacy"
TEMPLATE_PREFIX: Final = "nm-conf-template-"
GENERIC_HARDWARE: Final = "generic"
"""The hardware that names the generic network template; never a ``-generic`` suffix."""
GENERIC_TEMPLATE: Final = "nm-conf-template.bu"
"""``mc-files/templates/nm-conf-template.bu``: the network template for any hardware."""
BUTANE_SUFFIX: Final = ".bu"
MAX_CONFIG_NAME: Final = 253
MAX_HARDWARE_NAME: Final = 63
MAX_DEFAULT_CONFIGS: Final = 50

_CONFIG_NAME = re.compile(r"[a-z0-9]([-a-z0-9.]*[a-z0-9])?")
_HARDWARE_NAME = re.compile(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?")
_ENTRY_KEYS: Final = frozenset({"name", "hardware"})
_ENTRY_SHAPE: Final = "{name: <config>} or {name: nm-conf, hardware: <type>}"


@dataclass(frozen=True, slots=True)
class StaticConfig:
    """A static source a nodepool may name."""

    name: str
    path: RepoPath
    folder: str
    """Its folder under ``mc-files/``; ``""`` for the root."""


@dataclass(frozen=True, slots=True)
class HardwareType:
    """A hardware type: one ``templates/nm-conf-template-<name>.bu``, or the generic one."""

    name: str
    template: RepoPath

    @property
    def generic(self) -> bool:
        """The generic template, ``nm-conf-template.bu``, written as plain ``nm-conf``."""
        return self.name == GENERIC_HARDWARE


@dataclass(frozen=True, slots=True)
class ConfigEntry:
    """One ``configs`` entry as a person writes it."""

    name: str
    hardware: str | None = None

    def to_input(self) -> dict[str, str]:
        """The template-input shape: ``hardware`` only when set."""
        return {"name": self.name} | ({"hardware": self.hardware} if self.hardware else {})


def network_config_name(cluster_name: str, hardware: str) -> str:
    """``nm-conf-<clusterName>-<hw>``: the name a cluster file lists for its network config.

    The generic hardware is plain ``nm-conf``: the CI renders that name from
    the generic template, for any cluster.
    """
    if hardware == GENERIC_HARDWARE:
        return NETWORK_CONFIG
    return f"{NETWORK_CONFIG}-{cluster_name}-{hardware}"


def _is_config_name(name: str) -> bool:
    return len(name) <= MAX_CONFIG_NAME and _CONFIG_NAME.fullmatch(name) is not None


def _hardware_of(relative: Sequence[str]) -> str | None:
    """``("templates", "nm-conf-template-dell.bu")`` → ``dell``; anything else → ``None``.

    ``nm-conf-template.bu`` is the generic type; ``nm-conf-template-generic.bu``
    is no type (the name is reserved, and the catalogue says so).
    """
    if len(relative) != 2:  # templates/<file>: the CI does not look deeper
        return None
    filename = relative[1]
    if filename == GENERIC_TEMPLATE:
        return GENERIC_HARDWARE
    if not filename.startswith(TEMPLATE_PREFIX) or not filename.endswith(BUTANE_SUFFIX):
        return None
    hardware = filename.removeprefix(TEMPLATE_PREFIX).removesuffix(BUTANE_SUFFIX)
    if hardware == GENERIC_HARDWARE:
        return None
    if len(hardware) > MAX_HARDWARE_NAME or not _HARDWARE_NAME.fullmatch(hardware):
        return None
    return hardware


@dataclass(frozen=True, slots=True)
class _Candidate:
    order: tuple[int, int, tuple[str, ...]]
    path: RepoPath
    folder: str

    @property
    def in_legacy(self) -> bool:
        return self.folder.split("/", 1)[0] == LEGACY_DIR


@dataclass(frozen=True, slots=True)
class MachineConfigCatalog:
    """What ``mc-files/`` offers: static configs, hardware types, and what is wrong with it."""

    static: Mapping[str, StaticConfig] = field(default_factory=dict)
    hardware: Mapping[str, HardwareType] = field(default_factory=dict)
    legacy: frozenset[str] = frozenset()
    """Names the CI would take from ``legacy/``; Wingman refuses them."""
    problems: tuple[str, ...] = ()
    """Files that cannot be offered, and why (a name a template captures, a duplicate)."""

    @classmethod
    def from_files(  # noqa: C901 - baseline: the CI's file rules, in its order
        cls, files: Iterable[RepoPath], *, root: RepoPath = MC_FILES
    ) -> MachineConfigCatalog:
        """The catalogue of every file under ``root``, resolved in the CI's order."""
        depth = len(root.parts)
        hardware: dict[str, HardwareType] = {}
        problems: list[str] = []
        candidates: dict[str, list[_Candidate]] = {}
        for path in sorted(files, key=lambda p: p.parts):
            relative = path.parts[depth:]
            if path.parts[:depth] != root.parts or not relative:
                continue
            filename = relative[-1]
            if any(part.startswith(".") for part in relative) or filename.endswith(".md"):
                continue
            if relative[0] == TEMPLATES_DIR:
                found = _hardware_of(relative)
                if relative[-1] == f"{TEMPLATE_PREFIX}{GENERIC_HARDWARE}{BUTANE_SUFFIX}":
                    problems.append(
                        f"{path}: {GENERIC_HARDWARE!r} is reserved for the generic template "
                        f"{GENERIC_TEMPLATE}, so it is no hardware type"
                    )
                elif found is None:
                    problems.append(
                        f"{path}: not named {TEMPLATE_PREFIX}<hardware>{BUTANE_SUFFIX} directly in "
                        f"{TEMPLATES_DIR}/, so it is no hardware type"
                    )
                else:
                    hardware[found] = HardwareType(found, path)
                continue
            butane = filename.endswith(BUTANE_SUFFIX)
            name = filename.removesuffix(BUTANE_SUFFIX) if butane else filename
            order = (0 if butane else 1, 0 if len(relative) == 1 else 1, relative)
            candidates.setdefault(name, []).append(_Candidate(order, path, "/".join(relative[:-1])))
        catalog = cls(hardware=hardware)
        static: dict[str, StaticConfig] = {}
        legacy: set[str] = set()
        for name, found in sorted(candidates.items()):
            found.sort(key=lambda c: c.order)
            used = found[0]
            elsewhere = [str(c.path) for c in found if not c.in_legacy and c is not used]
            if used.in_legacy:
                legacy.add(name)
                if elsewhere:
                    problems.append(
                        f"{name}: the CI uses {used.path}, not {', '.join(elsewhere)}; "
                        f"Wingman does not offer {LEGACY_DIR}/ configs"
                    )
                continue
            template = catalog.template_for(name)
            if template is not None:
                problems.append(
                    f"{used.path}: the CI renders the generic network template for "
                    f"{NETWORK_CONFIG} instead of this file"
                    if template.generic
                    else f"{used.path}: the name ends in -{template.name}, so the CI renders the "
                    f"{template.name} network template for it instead of this file"
                )
                continue
            if not _is_config_name(name):
                problems.append(
                    f"{used.path}: {name!r} is not a usable config name (lowercase letters, "
                    f"digits, '-' and '.', at most {MAX_CONFIG_NAME} characters)"
                )
                continue
            if elsewhere:
                problems.append(f"{name}: also in {', '.join(elsewhere)}; the CI uses {used.path}")
            static[name] = StaticConfig(name, used.path, used.folder)
        return cls(static, hardware, frozenset(legacy), tuple(problems))

    def static_configs(self) -> list[StaticConfig]:
        """Static configs, the root's first, then by folder and name."""
        return sorted(self.static.values(), key=lambda c: (c.folder != "", c.folder, c.name))

    def hardware_types(self) -> list[HardwareType]:
        """Hardware types: the generic one first, then by name."""
        return sorted(self.hardware.values(), key=lambda h: (not h.generic, h.name))

    def template_for(self, name: str) -> HardwareType | None:
        """The network template the CI renders ``name`` from.

        Plain ``nm-conf`` is the generic template's (when there is one); any
        other name, the longest ``-<hw>`` it ends in. ``generic`` is never a suffix.
        """
        if name == NETWORK_CONFIG:
            return self.hardware.get(GENERIC_HARDWARE)
        typed = (h for h in self.hardware if h != GENERIC_HARDWARE)
        for hardware in sorted(typed, key=lambda h: (-len(h), h)):
            if name.endswith(f"-{hardware}"):
                return self.hardware[hardware]
        return None

    def hardware_choices(self) -> str:
        """The hardware types, for a message."""
        if not self.hardware:
            return f"mc-files/{TEMPLATES_DIR}/ has no {TEMPLATE_PREFIX}<hardware>{BUTANE_SUFFIX}"
        return "one of " + ", ".join(h.name for h in self.hardware_types())

    def did_you_mean(self, name: str) -> str:
        """A close static name or ``nm-conf``, for a message; empty when none is close."""
        close = difflib.get_close_matches(name, [*self.static, NETWORK_CONFIG], n=1, cutoff=0.8)
        return f" (did you mean {close[0]!r}?)" if close else ""


# ── Checking and expanding nodepool entries ──────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Rules:
    catalog: MachineConfigCatalog
    cluster_name: str | None
    """The chart's clusterName at create; ``None`` for a flavor or the defaults."""
    hardware_required: bool = True
    """``False`` only in the defaults, where the hardware type is chosen per nodepool."""


def _parse_entry(where: str, raw: object) -> tuple[ConfigEntry | None, list[str]]:
    if not isinstance(raw, Mapping):
        return None, [f"{where}: must be {_ENTRY_SHAPE}"]
    entry = cast("Mapping[object, object]", raw)
    problems: list[str] = []
    unknown = sorted(str(k) for k in entry if k not in _ENTRY_KEYS)
    if unknown:
        problems.append(
            f"{where}: unknown keys {', '.join(unknown)} (an entry has name and hardware)"
        )
    name, hardware = entry.get("name"), entry.get("hardware")
    if not isinstance(name, str) or not name:
        problems.append(f"{where}: name is required")
    if hardware is not None and not isinstance(hardware, str):
        problems.append(f"{where}: hardware must be a string")
    if problems or not isinstance(name, str):
        return None, problems
    return ConfigEntry(name, hardware if isinstance(hardware, str) and hardware else None), []


def _network_problems(where: str, entry: ConfigEntry, rules: _Rules) -> list[str]:
    catalog = rules.catalog
    if entry.hardware is None:
        if not rules.hardware_required:
            return []
        return [f"{where}: {NETWORK_CONFIG} needs a hardware type, {catalog.hardware_choices()}"]
    if entry.hardware not in catalog.hardware:
        if entry.hardware == GENERIC_HARDWARE:
            return [
                f"{where}: no generic network template mc-files/{TEMPLATES_DIR}/"
                f"{GENERIC_TEMPLATE}; {catalog.hardware_choices()}"
            ]
        return [f"{where}: no hardware type {entry.hardware!r}, {catalog.hardware_choices()}"]
    if rules.cluster_name is None:
        return []
    name = network_config_name(rules.cluster_name, entry.hardware)
    read_as = catalog.template_for(name)
    if read_as is not None and read_as.name != entry.hardware:
        return [
            f"{where}: the {entry.hardware} network config would be named {name!r}, which the "
            f"CI reads as hardware {read_as.name!r}"
        ]
    if not _is_config_name(name):
        return [f"{where}: {name!r} is longer than {MAX_CONFIG_NAME} characters"]
    return []


def _entry_problems(where: str, entry: ConfigEntry, rules: _Rules) -> list[str]:
    catalog = rules.catalog
    if entry.name == NETWORK_CONFIG:
        return _network_problems(where, entry, rules)
    if entry.hardware is not None:
        return [f"{where}: hardware applies only to {NETWORK_CONFIG}, not to {entry.name!r}"]
    template = catalog.template_for(entry.name)
    if template is not None:
        if rules.cluster_name is not None and entry.name == network_config_name(
            rules.cluster_name, template.name
        ):
            return []  # this cluster's own network config, written out by hand
        whose = "one cluster's" if rules.cluster_name is None else "another cluster's"
        return [
            f"{where}: {entry.name!r} is {whose} network config name; write "
            f"{{name: {NETWORK_CONFIG}, hardware: {template.name}}} instead"
        ]
    if entry.name in catalog.static:
        return []
    base = entry.name.removesuffix(BUTANE_SUFFIX)
    if base != entry.name and base in catalog.static:
        return [f"{where}: write {base!r} without {BUTANE_SUFFIX}: the CI names a butane config so"]
    if entry.name in catalog.legacy:
        return [
            f"{where}: {entry.name!r} is only in mc-files/{LEGACY_DIR}/ (restored originals of "
            "clusters not yet onboarded), which Wingman does not offer"
        ]
    return [
        f"{where}: no machine config {entry.name!r} in mc-files/{catalog.did_you_mean(entry.name)}"
    ]


def _list_problems(where: str, entries: Sequence[object], rules: _Rules) -> list[str]:
    problems: list[str] = []
    seen: dict[tuple[str, str | None], int] = {}
    for index, raw in enumerate(entries):
        at = f"{where}[{index}]"
        entry, shape = _parse_entry(at, raw)
        if entry is None:
            problems.extend(shape)
            continue
        found = _entry_problems(at, entry, rules)
        problems.extend(found)
        if found:
            continue
        key = (entry.name, entry.hardware)
        if key in seen:
            problems.append(f"{at}: the same entry as {where}[{seen[key]}]")
        else:
            seen[key] = index
    return problems


def _nodepool_config_lists(
    inputs: Mapping[str, object],
) -> tuple[list[tuple[str, Sequence[object]]], list[str]]:
    pools = inputs.get("nodepools")
    if pools is None:
        return [], []
    if not isinstance(pools, (list, tuple)):
        return [], ["nodepools: must be a list"]
    lists: list[tuple[str, Sequence[object]]] = []
    problems: list[str] = []
    for index, pool in enumerate(cast("Sequence[object]", pools)):
        if not isinstance(pool, Mapping):
            problems.append(f"nodepools[{index}]: must be a mapping")
            continue
        configs = cast("Mapping[str, object]", pool).get("configs")
        if configs is None:
            continue
        if not isinstance(configs, (list, tuple)):
            problems.append(f"nodepools[{index}].configs: must be a list of {_ENTRY_SHAPE}")
            continue
        lists.append((f"nodepools[{index}].configs", cast("Sequence[object]", configs)))
    return lists, problems


def _nodepool_problems(inputs: Mapping[str, object], rules: _Rules) -> list[str]:
    lists, problems = _nodepool_config_lists(inputs)
    for where, entries in lists:
        problems.extend(_list_problems(where, entries, rules))
    return problems


def flavor_config_problems(
    values: Mapping[str, object], catalog: MachineConfigCatalog
) -> list[str]:
    """Why a flavor's ``nodepools[i].configs`` presets break the rule; empty when they don't."""
    return _nodepool_problems(values, _Rules(catalog, None))


def cluster_config_problems(
    inputs: Mapping[str, object], catalog: MachineConfigCatalog, *, cluster_name: str
) -> list[str]:
    """Why a create's ``nodepools[i].configs`` break the rule, for the chart's ``cluster_name``."""
    return _nodepool_problems(inputs, _Rules(catalog, cluster_name))


def network_choice_problems(
    where: str, hardware: str, catalog: MachineConfigCatalog, *, cluster_name: str
) -> list[str]:
    """Why ``hardware`` cannot be a nodepool's network config for ``cluster_name``.

    The type must exist, and the CI must read the expanded name
    ``nm-conf-<clusterName>-<hw>`` as that type (an overlapping type can
    capture it).
    """
    return _network_problems(
        where, ConfigEntry(NETWORK_CONFIG, hardware), _Rules(catalog, cluster_name)
    )


def expand_network_configs(inputs: Mapping[str, object], *, cluster_name: str) -> dict[str, object]:
    """The inputs with each ``{name: nm-conf, hardware: <hw>}`` as ``{name: nm-conf-<c>-<hw>}``.

    Every other entry keeps only its ``name``. Inputs that are not the
    expected shape are left as they are; check them first with
    :func:`cluster_config_problems`. ``inputs`` is not changed.
    """
    pools = inputs.get("nodepools")
    if not isinstance(pools, (list, tuple)):
        return dict(inputs)
    expanded_pools: list[object] = []
    for pool in cast("Sequence[object]", pools):
        configs = (
            cast("Mapping[str, object]", pool).get("configs") if isinstance(pool, Mapping) else None
        )
        if not isinstance(configs, (list, tuple)):
            expanded_pools.append(pool)
            continue
        expanded: list[object] = []
        for raw in cast("Sequence[object]", configs):
            entry, _ = _parse_entry("", raw)
            if entry is None:
                expanded.append(raw)
            elif entry.name == NETWORK_CONFIG and entry.hardware is not None:
                expanded.append({"name": network_config_name(cluster_name, entry.hardware)})
            else:
                expanded.append({"name": entry.name})
        expanded_pools.append({**cast("Mapping[str, object]", pool), "configs": expanded})
    return {**inputs, "nodepools": expanded_pools}


# ── Nodepool defaults ────────────────────────────────────────────────────────


class _DefaultEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_CONFIG_NAME)
    hardware: str | None = Field(default=None, max_length=MAX_HARDWARE_NAME)


class _DefaultsDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configs: list[_DefaultEntry] = Field(default_factory=list, max_length=MAX_DEFAULT_CONFIGS)


@dataclass(frozen=True, slots=True)
class NodepoolDefaults:
    """The configs a new nodepool starts with (``nodepool-defaults.yaml``).

    They are served to the web app, which fills a nodepool with them when one
    is added. Day1 never applies them to a flavor or cluster that exists.
    """

    configs: tuple[ConfigEntry, ...] = ()


def parse_nodepool_defaults(content: str) -> NodepoolDefaults:
    """Parse ``nodepool-defaults.yaml``; an empty file is no defaults.

    Raises ``InvalidNodepoolDefaultsError`` with every problem found.
    """
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise InvalidNodepoolDefaultsError(
            "nodepool-defaults.yaml is not valid YAML", [str(exc)]
        ) from exc
    if document is None:
        return NodepoolDefaults()
    if not isinstance(document, dict):
        raise InvalidNodepoolDefaultsError("nodepool-defaults.yaml is not a YAML mapping")
    try:
        parsed = _DefaultsDocument.model_validate(document)
    except ValidationError as exc:
        raise InvalidNodepoolDefaultsError(
            "nodepool-defaults.yaml is not a valid defaults document",
            [
                f"{'.'.join(str(p) for p in e['loc']) or '(document)'}: {e['msg']}"
                for e in exc.errors()
            ],
        ) from exc
    return NodepoolDefaults(tuple(ConfigEntry(e.name, e.hardware or None) for e in parsed.configs))


def defaults_problems(defaults: NodepoolDefaults, catalog: MachineConfigCatalog) -> list[str]:
    """Default entries that would not resolve; ``nm-conf`` may leave hardware to the nodepool."""
    return _list_problems(
        "configs",
        [entry.to_input() for entry in defaults.configs],
        _Rules(catalog, None, hardware_required=False),
    )
