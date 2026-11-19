"""A nodepool that draws Agents from several InfraEnvs (ADR-0064).

An agent nodepool names its InfraEnv in ``infraEnvName``: the chart derives the
NodePool's name from it (``<clusterName>-<infraEnvName>``) and the team's
workflows read it. ``additionalInfraEnvNames`` lists more InfraEnvs it may draw
from; the chart then selects ``infraenvs.agent-install.openshift.io In`` the
first and these, in that order. A new Machine takes the first free Agent of
any of them, with no preference. Without the key the file, and the NodePool,
are what they always were. The template input is ``additional_infra_envs``.

``DAY1_MULTI_INFRAENV_NODEPOOLS`` turns it on (off by default): a
hostedclusters-setup chart that does not render the key selects the first
InfraEnv alone, silently. Off, Wingman never offers or writes the key, and an
edit leaves it as it is; a file that has it is still read.

Two rules keep the running nodes where they are, whatever the setting:

- **A NodePool is never renamed.** The first InfraEnv names it, so an edit that
  makes another InfraEnv first is refused: the chart would render a new
  NodePool, and every node would be replaced. To stop drawing from the first
  InfraEnv, the nodepool is replaced deliberately: removed in one merge
  request, a new one added in the next.
- **A Replace NodePool draws from the InfraEnvs it has.** On ``upgradeType:
  Replace`` a changed selector rolls every node; on ``InPlace`` (the chart's
  default) it touches none, and only Machines created afterwards follow it.

Each nodepool is matched with the file before the edit by ``name``, else
``infraEnvName``, as the replicas and version rules match them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final, cast

from wingman_day1.domain.errors import RenderError
from wingman_day1.domain.names import dns_label_problems
from wingman_day1.domain.template import TemplateField, analyze_template

FILE_KEY: Final = "additionalInfraEnvNames"
"""The cluster file's key: the InfraEnvs a nodepool draws from beside ``infraEnvName``."""
INPUT: Final = "additional_infra_envs"
"""The template input for :data:`FILE_KEY`, in each ``nodepools[]`` entry."""
FIRST_INPUT: Final = "infra_env"
SETTING: Final = "DAY1_MULTI_INFRAENV_NODEPOOLS"
MAX_ADDITIONAL: Final = 16
"""The most InfraEnvs one nodepool may draw from beside its own."""
REPLACE: Final = "Replace"
_KUBEVIRT: Final = "kubevirt"
_GUIDE: Final = "docs/upgrade/3.46-to-3.47.md"


def names_in(value: object) -> list[str] | None:
    """A list of InfraEnv names; empty for nothing, ``None`` when it is not a list of strings."""
    if value is None or value == "":
        return []
    if not isinstance(value, (list, tuple)):
        return None
    items = cast("Sequence[object]", value)
    if not all(isinstance(item, str) for item in items):
        return None
    return [cast("str", item) for item in items]


def additional_of(entry: Mapping[str, object]) -> tuple[str, ...]:
    """A file entry's ``additionalInfraEnvNames`` as written, leniently: its strings only."""
    raw = entry.get(FILE_KEY)
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in cast("list[object]", raw) if item is not None)


def nodepool_entries(
    values: Mapping[str, object], key: str
) -> list[tuple[int, Mapping[str, object]]]:
    """The mappings of the list at ``key`` (``nodepools`` or ``nodepool``), with their positions."""
    pools = values.get(key)
    if not isinstance(pools, (list, tuple)):
        return []
    items = cast("Sequence[object]", pools)
    return [
        (i, cast("Mapping[str, object]", p)) for i, p in enumerate(items) if isinstance(p, Mapping)
    ]


def infra_envs_of(first: str | None, additional: Iterable[str]) -> tuple[str, ...]:
    """Every InfraEnv a nodepool draws from: its own first, then the others, each once."""
    return tuple(dict.fromkeys(name for name in (first, *additional) if name))


def selected(entry: Mapping[str, object]) -> tuple[str, ...]:
    """The InfraEnvs the chart's selector holds for a file entry: sorted, each once."""
    first = entry.get("infraEnvName")
    return tuple(sorted(infra_envs_of(str(first) if first else None, additional_of(entry))))


# ── Create and flavor save: the template inputs ─────────────────────────────


def without_input(schema: Sequence[TemplateField]) -> list[TemplateField]:
    """The form schema without the nodepools' ``additional_infra_envs``: nothing offers it."""
    return [
        replace(field, fields=tuple(f for f in field.fields if f.name != INPUT))
        if field.name == "nodepools"
        else field
        for field in schema
    ]


def input_problems(inputs: Mapping[str, object], *, enabled: bool) -> list[str]:
    """Why the nodepools' ``additional_infra_envs`` inputs cannot be used (create, flavor save).

    Off, a nodepool may set none. On, each is an InfraEnv name (a DNS label),
    given once, not the nodepool's own, at most :data:`MAX_ADDITIONAL`, and
    never on KubeVirt, whose nodepools draw from no InfraEnv.
    """
    kubevirt = inputs.get("platform") == _KUBEVIRT
    problems: list[str] = []
    for index, pool in nodepool_entries(inputs, "nodepools"):
        names = names_in(pool.get(INPUT))
        if names == []:
            continue
        where = f"nodepools[{index}].{INPUT}"
        if not enabled:
            problems.append(
                f"{where}: a nodepool draws from its own InfraEnv only in this deployment "
                f"({SETTING} is off)"
            )
        elif names is None:
            problems.append(f"{where}: must be a list of InfraEnv names")
        else:
            problems += _names_problems(where, names, pool.get(FIRST_INPUT), kubevirt=kubevirt)
    return problems


def _names_problems(
    where: str, names: Sequence[str], first: object, *, kubevirt: bool
) -> list[str]:
    problems: list[str] = []
    if kubevirt:
        problems.append(f"{where}: a KubeVirt nodepool draws from no InfraEnv")
    if len(names) > MAX_ADDITIONAL:
        problems.append(f"{where}: {len(names)} InfraEnvs; the limit is {MAX_ADDITIONAL}")
    seen: set[str] = set()
    for position, name in enumerate(names):
        at = f"{where}[{position}]"
        problems += [f"{at}: {p}" for p in dns_label_problems(name, what="InfraEnv")]
        if name == first:
            problems.append(f"{at}: {name} is the nodepool's own InfraEnv already")
        elif name in seen:
            problems.append(f"{at}: {name} is listed twice")
        seen.add(name)
    return problems


def given(values: Mapping[str, object]) -> list[int]:
    """The positions of the nodepools that give ``additional_infra_envs``."""
    return [
        i for i, pool in nodepool_entries(values, "nodepools") if names_in(pool.get(INPUT)) != []
    ]


def template_problems(values: Mapping[str, object], template: str) -> list[str]:
    """Each nodepool that gives ``additional_infra_envs`` while ``template`` does not read it.

    Such a flavor would create clusters that draw from their first InfraEnv
    alone, so it is not saved until the specs project's template reads the
    input: the create form's own analysis of the template, as for image
    mirrors (ADR-0063). An empty template, or one that is not valid Jinja, is
    left to the create, which refuses both.
    """
    positions = given(values)
    if not positions or not template.strip():
        return []
    try:
        schema = analyze_template(template, include_reserved=True)
    except RenderError:
        return []
    pools = next((f for f in schema if f.name == "nodepools"), None)
    if pools is not None and any(f.name == INPUT for f in pools.fields):
        return []
    return [
        f"nodepools[{i}].{INPUT}: the specs project's cluster-template.j2 does not read this "
        "input, so a cluster created from this flavor would draw from its first InfraEnv "
        f"alone; add the template line in {_GUIDE} (ADR-0064)"
        for i in positions
    ]


def rendered_problems(inputs: Mapping[str, object], rendered: Mapping[str, object]) -> list[str]:
    """Each rendered nodepool whose ``additionalInfraEnvNames`` is not what it chose.

    The guard against a specs-project template that does not render the input:
    the file would silently draw from the first InfraEnv alone. Also refused,
    a template that writes the key unasked: without extras the file is as before.
    """
    chosen = dict(nodepool_entries(inputs, "nodepools"))
    problems: list[str] = []
    for index, pool in nodepool_entries(rendered, "nodepool"):
        want = names_in(chosen.get(index, {}).get(INPUT)) or []
        if (names_in(pool.get(FILE_KEY)) or []) != want or (FILE_KEY in pool and not want):
            problems.append(
                f"nodepool[{index}].{FILE_KEY}: the template wrote {pool.get(FILE_KEY)!r} for "
                f"{want}; the specs project's cluster-template.j2 must render {INPUT} as given "
                f"({_GUIDE})"
            )
    return problems


# ── Edits of an existing file ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Pool:
    index: int
    key: str
    entry: Mapping[str, object]

    @property
    def named(self) -> bool:
        return bool(self.entry.get("name"))

    @property
    def first(self) -> str | None:
        found = self.entry.get("infraEnvName")
        return str(found) if found else None

    @property
    def infra_envs(self) -> frozenset[str]:
        return frozenset(selected(self.entry))

    @property
    def replace(self) -> bool:
        return self.entry.get("upgradeType") == REPLACE


def _pools(values: Mapping[str, object]) -> list[_Pool]:
    return [
        _Pool(index, str(entry.get("name") or entry.get("infraEnvName") or f"#{index}"), entry)
        for index, entry in nodepool_entries(values, "nodepool")
    ]


def edit_problems(
    old: Mapping[str, object], new: Mapping[str, object], *, enabled: bool
) -> list[str]:
    """Why an edit's InfraEnvs may not be proposed; empty when they may (see the module)."""
    before = {pool.key: pool for pool in _pools(old)}
    after = _pools(new)
    problems: list[str] = []
    for pool in after:
        was = before.get(pool.key)
        where = f"nodepool[{pool.index}]"
        if pool.entry.get(FILE_KEY) != (was.entry.get(FILE_KEY) if was else None):
            problems += (
                file_problems(where, pool.entry, kubevirt=new.get("platform") == _KUBEVIRT)
                if enabled
                else [
                    f"{where}: {FILE_KEY} is not written in this deployment ({SETTING} is "
                    "off); an edit must leave it as it is"
                ]
            )
        if was is not None and _rolls(was, pool):
            problems.append(
                f"{where}: NodePool {pool.key} is upgradeType Replace, so a change to the "
                "InfraEnvs it draws from would replace every node; leave them as they are"
            )
    return problems + _renamed(before, after)


def _rolls(was: _Pool, pool: _Pool) -> bool:
    """A Replace NodePool with more than one InfraEnv, before or after, whose InfraEnvs change."""
    several = bool(additional_of(was.entry) or additional_of(pool.entry))
    return several and (was.replace or pool.replace) and pool.infra_envs != was.infra_envs


def _renamed(before: Mapping[str, _Pool], after: Sequence[_Pool]) -> list[str]:
    """A nodepool that takes another one's InfraEnvs under a new first InfraEnv: a new NodePool."""
    keys = {pool.key for pool in after}
    gone = [pool for key, pool in before.items() if key not in keys and not pool.named]
    problems: list[str] = []
    for pool in after:
        if pool.key in before:
            continue
        for old in gone:
            several = len(old.infra_envs) > 1 or len(pool.infra_envs) > 1
            if several and pool.first != old.first and old.infra_envs & pool.infra_envs:
                problems.append(
                    f"nodepool[{pool.index}]: its first InfraEnv is {pool.first}, but the "
                    f"NodePool it replaces is named after {old.first}, which it drew from "
                    f"first; a new first InfraEnv is a new NodePool, and every node would be "
                    f"replaced. Keep {old.first} as infraEnvName and list the others in "
                    f"{FILE_KEY}, or remove the old nodepool in a merge request of its own"
                )
                break
    return problems


def file_problems(where: str, entry: Mapping[str, object], *, kubevirt: bool) -> list[str]:
    """Why one file entry's ``additionalInfraEnvNames`` breaks the chart's rule; empty when not."""
    if FILE_KEY not in entry:
        return []
    names = names_in(entry[FILE_KEY])
    if names is None:
        return [f"{where}.{FILE_KEY}: must be a list of InfraEnv names"]
    problems = _names_problems(
        f"{where}.{FILE_KEY}", names, entry.get("infraEnvName"), kubevirt=kubevirt
    )
    if names and not entry.get("infraEnvName"):
        problems.append(
            f"{where}: {FILE_KEY} needs infraEnvName, the InfraEnv that names the NodePool"
        )
    selector = entry.get("agentLabelSelector")
    if names and isinstance(selector, Mapping) and "nodeLabelKey" in selector:
        problems.append(
            f"{where}: {FILE_KEY} cannot be combined with agentLabelSelector; set infraEnvName"
        )
    return problems
