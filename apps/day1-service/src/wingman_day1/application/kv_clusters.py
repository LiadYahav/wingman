"""Create a KV cluster on a seed through provision-cluster (ADR-0069).

A KV cluster is a hosted cluster whose hub is its zone's seed (ADR-0067), and
every one is the same: the draft fills the whole file from the seed, its
InfraEnvs and a model KV cluster (``domain/kv_create.py``), and the create
renders it through the specs project's ``cluster-template.j2`` with the same
checks as a tenant's file (``rendered_file.render_new_file``), then starts
the platform's provision-cluster with ``mce=<seed>`` (ADR-0042). Never
retried (ADR-0006). A tenant's create (``clusters.py``) still refuses a seed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from wingman_core.domain.cluster_kinds import HostedClusterKind, MceKind, mce_kind
from wingman_core.domain.users import User
from wingman_day1.application.clusters import ClusterService
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.application.provision_mrs import provision_merge_requests
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.application.tree import Day1Tree, read_tree
from wingman_day1.domain.cluster_file import NO_WORKFLOW_KEYS, WorkflowKeys, load_values
from wingman_day1.domain.cluster_file import read_values as values_of
from wingman_day1.domain.errors import (
    HubNotConfiguredError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleError,
)
from wingman_day1.domain.kind_names import describe_seed
from wingman_day1.domain.kv_clusters import kv_zone_problems
from wingman_day1.domain.kv_create import (
    DEFAULT_KV_WORKERS,
    KvModel,
    KvPool,
    choose_model,
    default_version,
    kv_inputs,
    kv_name_problems,
    model_of,
    next_kv_name,
    owner_gaps,
    pool_zone,
    version_choices,
    workers_problems,
    zone_pools,
    zones_of,
)
from wingman_day1.domain.names import HOSTED_CLUSTER_PREFIX, HostedClusterNaming, MceNaming
from wingman_day1.domain.openshift_versions import unhostable_problems
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.rendered_file import render_new_file
from wingman_day1.domain.template import build_inputs, check_inputs
from wingman_day1.domain.workflows import ProvisionRun
from wingman_day1.ports import ProvisionWorkflow, RepoReads

logger = logging.getLogger(__name__)

InfraEnvNames = Callable[[str], Awaitable[Sequence[str]]]
"""The InfraEnv names on a hub, read live (``StatusService.infra_envs``)."""


@dataclass(frozen=True, slots=True)
class KvChoices:
    """What an admin chose in the dialog; anything left out is the draft's own pick."""

    zone: str | None = None
    infra_env: str | None = None
    mastertag: str | None = None
    workers: int = DEFAULT_KV_WORKERS
    owner: Mapping[str, str] = field(default_factory=dict)
    """Only read when no KV cluster exists to copy the owner from."""


@dataclass(frozen=True, slots=True)
class KvDraft:
    """The new KV cluster's file as Wingman fills it, and why it cannot be created yet."""

    seed: str
    site: str
    name: str | None
    zone: str | None
    zones: tuple[str, ...]
    mastertag: str | None
    versions: tuple[str, ...]
    infra_env: str | None
    infra_envs: tuple[str, ...]
    """The zone's bare-metal InfraEnvs to choose from."""
    infra_envs_from: str
    """``hub`` (read live) or ``files`` (what the seed's KV clusters name)."""
    workers: int
    model: KvModel | None
    owner: Mapping[str, str]
    content: str | None
    """The rendered file; ``None`` while ``problems`` say why not."""
    problems: tuple[str, ...]

    @property
    def ref(self) -> ClusterRef | None:
        """Where the file goes, once it has a name."""
        return ClusterRef(self.site, self.seed, self.name) if self.name else None


@dataclass(slots=True)
class _Found:
    """What a draft has read and picked so far, and its problems."""

    problems: list[str] = field(default_factory=list)

    def pick(self, choice: str | None, options: Sequence[str], *, what: str) -> str | None:
        """``choice`` when it is one of ``options``; the one option; else a problem."""
        if choice:
            if choice in options:
                return choice
            self.problems.append(f"{what} {choice!r} is not one of: {', '.join(options) or 'none'}")
            return None
        if len(options) == 1:
            return options[0]
        if options:
            self.problems.append(f"choose the {what}: {', '.join(options)}")
        return None


class KvClusterService:
    """The KV cluster create: a draft, then provision-cluster on the seed."""

    def __init__(
        self,
        day1: RepoReads,
        clusters: ClusterService,
        sites: SiteCatalog,
        specs: SpecCatalog,
        machine_configs: MachineConfigService,
        *,
        provision: ProvisionWorkflow,
        naming: HostedClusterNaming,
        owned: WorkflowKeys = NO_WORKFLOW_KEYS,
        hub_infra_envs: InfraEnvNames | None = None,
    ) -> None:
        """Read the day1 repo; ``hub_infra_envs`` reads live, ``None`` with live status off."""
        self._day1 = day1
        self._clusters = clusters
        self._sites = sites
        self._specs = specs
        self._machine_configs = machine_configs
        self._provision = provision
        self._naming = naming
        self._owned = owned
        self._hub_infra_envs = hub_infra_envs

    async def draft(self, seed: str, choices: KvChoices | None = None) -> KvDraft:
        """The new KV cluster on ``seed`` with ``choices``; a seed that is not one is 404."""
        choices = choices or KvChoices()
        tree = await read_tree(self._day1)
        site = _site_of(tree, seed)
        naming = describe_seed(seed, site=site)
        models = await self._models(tree)
        model = choose_model(models, seed=seed, site=site)
        infra_envs, source = await self._infra_envs(seed, site, models)
        found = _Found(problems=workers_problems(choices.workers))
        zones = (naming.zone,) if naming.zone else zones_of(infra_envs)
        zone = found.pick(choices.zone, zones, what="zone")
        if not zones:
            found.problems.append(f"seed {seed}'s name gives no zone, and no InfraEnv names one")
        name = await self._name(tree, naming, zone, found)
        offered, mastertag = await self._version(seed, site, choices.mastertag, found)
        pools = _zone_pools(infra_envs, zone, model)
        infra_env = found.pick(choices.infra_env, pools, what="InfraEnv") if zone else None
        if zone and not pools:
            found.problems.append(
                f"seed {seed} has no bare-metal InfraEnv <flavor>-mtl-{zone} ({source})"
            )
        owner = dict(model.owner) if model else dict(choices.owner)
        if gaps := owner_gaps(owner):
            whose = f"{model.ref.name}'s owner" if model else "with no KV cluster to copy, owner"
            found.problems.append(f"{whose} lacks {', '.join(gaps)}")
        draft = KvDraft(
            seed=seed,
            site=site,
            name=name,
            zone=zone,
            zones=zones,
            mastertag=mastertag,
            versions=offered,
            infra_env=infra_env,
            infra_envs=pools,
            infra_envs_from=source,
            workers=choices.workers,
            model=model,
            owner=owner,
            content=None,
            problems=tuple(found.problems),
        )
        return await self._rendered(draft)

    async def create(self, seed: str, name: str, choices: KvChoices, *, user: User) -> ProvisionRun:
        """Start provision-cluster for the draft's file, if it is still ``name`` (ADR-0042)."""
        draft = await self.draft(seed, choices)
        if draft.content is None:
            raise InvalidInputError(
                f"no KV cluster can be created on {seed} as chosen", draft.problems
            )
        if draft.name != name:
            raise StaleError(
                f"the next free KV cluster name on {seed} is now {draft.name}, not {name}; reload"
            )
        logger.info(
            "%s starts provision-cluster for KV cluster %s on seed %s (site %s), a copy of %s",
            user.username,
            name,
            seed,
            draft.site,
            draft.model.ref.name if draft.model else "no KV cluster",
        )
        return await self._provision.start(
            cluster=name.removeprefix(HOSTED_CLUSTER_PREFIX), mce=seed, content=draft.content
        )

    # ── Reads ───────────────────────────────────────────────────────────────

    async def _models(self, tree: Day1Tree) -> list[KvModel]:
        """Every KV cluster whose file parses, as a model."""
        refs = [ref for ref in tree.clusters if ref.kind is HostedClusterKind.KV]
        read = await asyncio.gather(*(self._clusters.values(ref) for ref in refs))
        return [model_of(ref, values) for ref, values in zip(refs, read, strict=True) if values]

    async def _infra_envs(
        self, seed: str, site: str, models: Sequence[KvModel]
    ) -> tuple[tuple[str, ...], str]:
        """The seed's InfraEnvs from its hub, else the ones its KV clusters' files name.

        A hub day1 has no access to (``HubNotConfiguredError``) is read as with
        live status off; any other hub error is raised.
        """
        if self._hub_infra_envs is not None:
            try:
                return tuple(await self._hub_infra_envs(seed)), "hub"
            except HubNotConfiguredError:
                pass
        on_seed = [m for m in models if (m.ref.site, m.ref.mce) == (site, seed)]
        return tuple(name for m in on_seed for name in m.infra_envs), "files"

    async def _name(
        self, tree: Day1Tree, naming: MceNaming, zone: str | None, found: _Found
    ) -> str | None:
        """The next free ``ocp4-<lc>-kv-<site>-<zone>-<id>``; taken by files and open creates."""
        if naming.env is None:
            found.problems.append(
                f"seed {naming.name}'s name gives no lifecycle (prod, prep or test) for the "
                "KV cluster's name"
            )
            return None
        if zone is None:
            return None
        taken = {ref.name for ref in tree.clusters}
        taken.update(p.stem for p in await provision_merge_requests(self._day1))
        name = next_kv_name(naming.env, site=naming.site, zone=zone, taken=taken)
        if name is None:
            found.problems.append(f"every KV cluster id from a to z is taken in {zone}")
            return None
        found.problems.extend(kv_name_problems(name, site=naming.site, naming=self._naming))
        return name

    async def _version(
        self, seed: str, site: str, choice: str | None, found: _Found
    ) -> tuple[tuple[str, ...], str | None]:
        """The seed's offered releases and the one picked: the choice, else its default."""
        offered = await self._sites.openshift_versions(seed)
        default = await self._sites.default_mastertag(site, seed)
        mastertag = choice or default_version(default, offered.versions)
        if mastertag is None:
            found.problems.extend([f"seed {seed} offers no OpenShift version", *offered.problems])
        else:
            found.problems.extend(unhostable_problems(mastertag, offered))
        return version_choices(default, offered.versions), mastertag

    # ── The file ────────────────────────────────────────────────────────────

    async def _rendered(self, draft: KvDraft) -> KvDraft:
        """The draft with its file, or with why the file cannot be made."""
        ref, zone, infra_env = draft.ref, draft.zone, draft.infra_env
        if draft.problems or not (ref and zone and infra_env and draft.mastertag):
            return draft
        try:
            content = await self._render(draft, ref, KvPool(infra_env, draft.workers, zone))
        except InvalidInputError as exc:
            return replace(draft, problems=(str(exc), *exc.problems))
        return replace(draft, content=content)

    async def _render(self, draft: KvDraft, ref: ClusterRef, pool: KvPool) -> str:
        model = draft.model
        model_cluster = self._naming.for_file(model.ref.name).cluster_name if model else ""
        inputs = build_inputs(
            variables=kv_inputs(pool, owner=draft.owner, model=model, model_cluster=model_cluster),
            cluster_name=ref.name,
            site=ref.site,
            mce=ref.mce,
            openshift_release_version=draft.mastertag,
        )
        if problems := check_inputs(inputs):
            raise InvalidInputError("the KV cluster's inputs are not acceptable", problems)
        rendered = render_new_file(
            await self._specs.template(),
            inputs,
            catalog=await self._machine_configs.catalog(),
            tuning=await self._machine_configs.tuning(),
            owned=self._owned,
            cluster_name=self._naming.for_file(ref.name).cluster_name,
        )
        written = values_of(load_values(rendered)).nodepools
        if problems := kv_zone_problems(pool.zone, written):
            raise InvalidInputError(
                "the specs project's cluster-template.j2 does not write the KV cluster's zone "
                "(nodepools[].node_labels as nodeLabels)",
                problems,
            )
        return rendered


def _site_of(tree: Day1Tree, seed: str) -> str:
    """The site whose folder holds ``seed``; a missing or non-seed folder is 404."""
    sites = [site for site, mce in tree.mces if mce == seed and mce_kind(mce) is MceKind.SEED]
    if len(sites) != 1:
        raise ResourceNotFoundError(f"seed {seed!r} does not exist in the day1 repo")
    return sites[0]


def _zone_pools(
    infra_envs: Sequence[str], zone: str | None, model: KvModel | None
) -> tuple[str, ...]:
    """The zone's bare-metal InfraEnvs; none found, the model's own when it is the zone's."""
    if zone is None:
        return ()
    pools = zone_pools(infra_envs, zone)
    if pools or model is None:
        return pools
    return tuple(name for name in model.infra_envs[:1] if pool_zone(name) == zone)
