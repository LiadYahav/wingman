"""The hosted-cluster values file and who owns which of its keys (ADR-0012).

A cluster file is the last values layer of the hostedclusters-setup chart.
People (and Wingman) write ``owner``, ``mastertag``, ``nodepool[]`` and
optional fields such as ``platform: kubevirt``. Automation writes the rest on
the merge request's branch, after Wingman's commit:

- ``vlanId`` and ``dhcp_values``: the allocate-segment workflow;
- ``mcFiles`` and ``mcConfigMap``: the day1 CI pipeline.

Wingman never writes those keys, and never changes them when it edits a
file. ``clusterName``, ``site`` and ``mce`` come from the file's path; a
rendered file must not set them either.

Wingman's own bookkeeping lives in a comment header, which Helm, ArgoCD and
the CI scripts (they rewrite files preserving formatting) all ignore::

    # specName: "agent-standard"
    # specVersion: "1.0.0"
    # wingmanAddons: [{"team": "redbull", "name": "cluster-roles", ...}]

The first two lines are the legacy service's, so files it created still
link to their spec. Nothing else is ever written into ``hostedClusters/``:
every file there becomes an Argo Application.
"""

from __future__ import annotations

import json
import re
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

import yaml
from yaml.constructor import ConstructorError
from yaml.resolver import BaseResolver

from wingman_day1.domain.addons import RequestedAddon
from wingman_day1.domain.errors import InvalidClusterFileError
from wingman_day1.domain.upgrades import version_problems

AUTOMATION_KEYS: Final = ("vlanId", "dhcp_values", "mcFiles", "mcConfigMap")
"""Written on the MR branch by the allocate-segment workflow and CI; never by Wingman."""
PATH_KEYS: Final = ("clusterName", "site", "mce")
"""Passed by the ApplicationSet from the file's path; a rendered file must not set them."""

_MASTERTAG = re.compile(r"^\d+\.\d+\.\d+(?:-[a-z0-9_]+)?$")
_HEADER = re.compile(r"^#\s*(?P<key>specName|specVersion|wingmanAddons):\s?(?P<value>.*)$")
_PLATFORM_KUBEVIRT: Final = "kubevirt"


# ── Strict YAML: one document, no duplicate keys ─────────────────────────────


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys, which PyYAML would silently collapse."""


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode) -> dict[Hashable, object]:
    seen: set[object] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node)
        if key in seen:
            raise ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node)


_StrictLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_values(content: str) -> dict[str, object]:
    """Parse a values file: exactly one YAML document, a mapping, no duplicate keys.

    An empty file is an empty mapping. Raises ``InvalidClusterFileError`` with
    the line and column of a syntax error.
    """
    try:
        documents = [d for d in yaml.load_all(content, Loader=_StrictLoader) if d is not None]
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise InvalidClusterFileError(
            f"not valid YAML{where}", [f"{exc.problem or exc}{where}"]
        ) from exc
    except yaml.YAMLError as exc:
        raise InvalidClusterFileError("not valid YAML", [str(exc)]) from exc
    if len(documents) > 1:
        raise InvalidClusterFileError(
            "a values file is one YAML document",
            [f"found {len(documents)} documents; Helm reads only a single values mapping"],
        )
    if not documents:
        return {}
    document = documents[0]
    if not isinstance(document, dict):
        raise InvalidClusterFileError(
            "a values file is a YAML mapping", [f"the document is a {type(document).__name__}"]
        )
    return {str(k): v for k, v in document.items()}


# ── The header Wingman keeps in comments ─────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Provenance:
    """What the comment header says about where a cluster file came from."""

    spec_name: str | None = None
    spec_version: str | None = None
    requested_addons: tuple[RequestedAddon, ...] = ()
    problems: tuple[str, ...] = ()


def read_provenance(content: str) -> Provenance:
    """Read the leading comment lines; stops at the first line that is not a comment."""
    values: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            break
        match = _HEADER.match(stripped)
        if match:
            values.setdefault(match["key"], match["value"].strip())
    addons, problems = _parse_addons(values.get("wingmanAddons"))
    return Provenance(
        spec_name=_unquote(values.get("specName")),
        spec_version=_unquote(values.get("specVersion")),
        requested_addons=addons,
        problems=problems,
    )


def _unquote(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().strip("\"'") or None


def _parse_addons(raw: str | None) -> tuple[tuple[RequestedAddon, ...], tuple[str, ...]]:
    if raw is None:
        return (), ()
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            raise TypeError("not a list")
        return tuple(
            RequestedAddon(
                team=str(item["team"]),
                name=str(item["name"]),
                version=str(item["version"]),
                override_values=dict(item.get("override_values") or {}),
            )
            for item in items
        ), ()
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return (), (f"the wingmanAddons header line is unreadable: {type(exc).__name__}",)


def is_header_line(line: str) -> bool:
    """Whether ``line`` is one of Wingman's header lines (``# specName: ...`` and the like)."""
    return _HEADER.match(line.strip()) is not None


def provenance_lines(provenance: Provenance) -> list[str]:
    """The header lines Wingman writes for ``provenance``, in order, without line endings."""
    lines: list[str] = []
    if provenance.spec_name:
        lines.append(f'# specName: "{provenance.spec_name}"')
    if provenance.spec_version:
        lines.append(f'# specVersion: "{provenance.spec_version}"')
    if provenance.requested_addons:
        payload = [
            {
                "team": a.team,
                "name": a.name,
                "version": a.version,
                "override_values": dict(a.override_values),
            }
            for a in provenance.requested_addons
        ]
        lines.append(f"# wingmanAddons: {json.dumps(payload, sort_keys=True)}")
    return lines


def with_provenance(body: str, provenance: Provenance) -> str:
    """``body`` with the header for ``provenance`` in front (the header Wingman writes)."""
    header = "\n".join(provenance_lines(provenance))
    return f"{header}\n{body}" if header else body


# ── Reading the values ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class NodePoolValues:
    """One ``nodepool[]`` entry, as written."""

    name: str | None
    infra_env_name: str | None
    replicas: int | None
    allow_deletion: object
    configs: tuple[str, ...]
    node_labels: Mapping[str, object]
    tuning_config: object


@dataclass(frozen=True, slots=True)
class ClusterValues:
    """A cluster file's values, read for display; :func:`load_values` holds the raw mapping."""

    owner: Mapping[str, object] | None
    mastertag: str | None
    platform: str
    nodepools: tuple[NodePoolValues, ...]
    vlan_id: object
    dhcp_network: str | None
    cluster_name: str | None
    """An explicit ``clusterName`` key; it overrides the one derived from the file name."""
    automation_keys: tuple[str, ...] = field(default=())
    """Which automation-owned keys the file already carries."""


def read_values(values: Mapping[str, object]) -> ClusterValues:
    """Pick out what day1 shows from a parsed values mapping (lenient: never raises)."""
    owner = values.get("owner")
    dhcp = values.get("dhcp_values")
    raw_pools = values.get("nodepool")
    pools = raw_pools if isinstance(raw_pools, list) else []
    explicit = values.get("clusterName")
    return ClusterValues(
        owner=owner if isinstance(owner, dict) else None,
        mastertag=_text(values.get("mastertag")),
        platform=_text(values.get("platform")) or "agent",
        nodepools=tuple(_nodepool(p) for p in pools if isinstance(p, dict)),
        vlan_id=values.get("vlanId"),
        dhcp_network=_text(dhcp.get("network")) if isinstance(dhcp, dict) else None,
        cluster_name=_text(explicit),
        automation_keys=tuple(k for k in AUTOMATION_KEYS if k in values),
    )


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def _nodepool(raw: Mapping[str, object]) -> NodePoolValues:
    labels = raw.get("labels")
    configs = raw.get("configs")
    node_labels = raw.get("nodeLabels")
    replicas = raw.get("replicas")
    return NodePoolValues(
        name=_text(raw.get("name")),
        infra_env_name=_text(raw.get("infraEnvName")),
        replicas=replicas if isinstance(replicas, int) and not isinstance(replicas, bool) else None,
        allow_deletion=labels.get("allowDeletion") if isinstance(labels, dict) else None,
        configs=tuple(str(c["name"]) for c in configs or [] if isinstance(c, dict) and "name" in c)
        if isinstance(configs, list)
        else (),
        node_labels=node_labels if isinstance(node_labels, dict) else {},
        tuning_config=raw.get("tuningConfig"),
    )


# ── The rules ────────────────────────────────────────────────────────────────


def _mastertag_problems(values: Mapping[str, object]) -> list[str]:
    tag = values.get("mastertag")
    if tag is None or tag == "":
        return ["mastertag is required"]
    if not isinstance(tag, str) or not _MASTERTAG.match(tag):
        return [f"mastertag {tag!r} is not an OpenShift release like 4.18.22 or 4.18.22-x86_64"]
    return []


def _nodepool_problems(values: Mapping[str, object], *, required: bool) -> list[str]:
    """The chart's own nodepool rules (templates/nodepool.yaml), checked before Helm does."""
    if "nodepool" not in values:
        return ["nodepool must list at least one nodepool"] if required else []
    pools = values["nodepool"]
    if not isinstance(pools, list) or (required and not pools):
        return ["nodepool must list at least one nodepool"]
    kubevirt = values.get("platform") == _PLATFORM_KUBEVIRT
    problems: list[str] = []
    seen: set[str] = set()
    for index, pool in enumerate(pools):
        where = f"nodepool[{index}]"
        if not isinstance(pool, dict):
            problems.append(f"{where} must be a mapping")
            continue
        infra_env, name = pool.get("infraEnvName"), pool.get("name")
        if not kubevirt and not infra_env:
            problems.append(f"{where}: infraEnvName is required on the Agent platform")
        if not (name or infra_env):
            problems.append(f"{where}: needs infraEnvName or an explicit name")
        replicas = pool.get("replicas")
        if replicas is not None and (
            isinstance(replicas, bool) or not isinstance(replicas, int) or replicas < 0
        ):
            problems.append(f"{where}: replicas must be a whole number of at least 0")
        derived = str(name) if name else f"<clusterName>-{infra_env}"
        if derived in seen:
            problems.append(
                f"{where}: nodepool name {derived!r} is used twice; nodepools that share an "
                "InfraEnv must each set name"
            )
        seen.add(derived)
    return problems


def rendered_file_problems(content: str) -> list[str]:
    """Why a freshly rendered cluster file breaks the contract; empty when it is valid."""
    try:
        values = load_values(content)
    except InvalidClusterFileError as exc:
        return list(exc.problems)
    problems = _mastertag_problems(values) + _nodepool_problems(values, required=True)
    problems += [
        f"{key} is written by automation (the allocate-segment workflow or CI), never by Wingman"
        for key in AUTOMATION_KEYS
        if key in values
    ]
    problems += [
        f"{key} comes from the file's path; the cluster file must not set it"
        for key in PATH_KEYS
        if key in values
    ]
    return problems


def edit_problems(current: str, edited: str, *, versions_by_workflow: bool = False) -> list[str]:
    """Why an edit of an existing cluster file may not be proposed; empty when it may.

    Keys owned by automation, and ``clusterName`` (which would rename the
    cluster), must keep exactly the values they have in ``current``. With
    ``versions_by_workflow`` (``DAY1_UPGRADES``, ADR-0055), so must the version
    keys the upgrade workflow owns (``upgrades.version_problems``).
    """
    try:
        new = load_values(edited)
    except InvalidClusterFileError as exc:
        return list(exc.problems)
    try:
        old = load_values(current)
    except InvalidClusterFileError:
        old = {}
    problems = _mastertag_problems(new) + _nodepool_problems(new, required=False)
    for key in (*AUTOMATION_KEYS, "clusterName"):
        if old.get(key) != new.get(key):
            owner = "automation" if key in AUTOMATION_KEYS else "the file name"
            problems.append(f"{key} is owned by {owner}; an edit must leave it as it is")
    problems += [
        f"{key} comes from the file's path; the cluster file must not set it"
        for key in ("site", "mce")
        if key in new and old.get(key) != new.get(key)
    ]
    if versions_by_workflow:
        problems += version_problems(old, new)
    return problems


def require_valid(problems: Sequence[str], *, message: str) -> None:
    """Raise ``InvalidClusterFileError`` when there are problems."""
    if problems:
        raise InvalidClusterFileError(message, problems)


def describe_for_review(values: ClusterValues) -> str:
    """One paragraph a reviewer reads in the MR description."""
    lines = [f"- mastertag: `{values.mastertag or '(none)'}`", f"- platform: `{values.platform}`"]
    for pool in values.nodepools:
        label = pool.name or pool.infra_env_name or "?"
        replicas = pool.replicas if pool.replicas is not None else 1
        configs = ", ".join(pool.configs) or "none"
        lines.append(
            f"- nodepool `{label}`: InfraEnv `{pool.infra_env_name}`, "
            f"{replicas} replicas, configs: {configs}"
        )
    return "\n".join(lines)
