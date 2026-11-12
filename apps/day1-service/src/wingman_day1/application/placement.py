"""MCE placement: the candidates for a new cluster, their numbers, and the pick (ADR-0050).

The rule is pure (``wingman_day1.domain.placement``); this reads what it
needs:

- the candidates and the versions each hosts, from the day1 repo (ADR-0034);
- each candidate's clusters and this owner's, from its cluster files and the
  open Wingman merge requests that create a cluster there (each MR's diff
  says where, and its file says the owner);
- each candidate's free pods, from its own nodes and pods, read when asked
  (a cache of seconds, shared; never the minutes another source would be);
- each candidate's healthy free servers of every node type the new cluster
  needs: its free Agents in those InfraEnvs, joined to server-scan's servers.
  The needs come from the form (each nodepool's InfraEnv and replicas), else
  from the flavor's presets, and at create from the rendered file;
- each candidate's spare servers, from server-scan's fleet rows (cached as
  for the nodes view).

Without live MCE reads (no hub: ``CLUSTER_STATUS_ENABLED`` off) placement
still runs, on the day1 repo and server-scan: the free pods, the servers of
each node type and the hub read are ``not_checked`` and do not block a pick.

A source that cannot be read makes its numbers unknown, never zero: an MCE
whose nodes or pods cannot be read fails the ``readable`` check; server-scan
not answering makes every spare count unknown. The day1 repo itself must be
read, so its errors propagate.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from wingman_core.domain.errors import GitError, NotFoundError
from wingman_core.domain.git import FileDiff
from wingman_core.domain.merge_request import MergeRequest, MRState
from wingman_core.domain.mr_conventions import (
    WINGMAN_LABEL,
    Repo,
    ResourceType,
    Verb,
    parse_mr_title,
)
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.application.tree import Day1Tree, read_tree
from wingman_day1.domain.cluster_file import load_values, read_values
from wingman_day1.domain.errors import (
    HubDeniedError,
    HubError,
    HubNotConfiguredError,
    InvalidClusterFileError,
    InvalidInputError,
    ServerScanUnavailableError,
)
from wingman_day1.domain.machines import AgentObservation
from wingman_day1.domain.mce_capacity import (
    FreePods,
    free_pods,
    node_type_supply,
    spare_servers,
    summed_needs,
)
from wingman_day1.domain.names import Env, describe_mce, dns_label_problems
from wingman_day1.domain.openshift_versions import bare_release, is_release
from wingman_day1.domain.owners import MAX_OWNER_DIGITS
from wingman_day1.domain.paths import ClusterRef, parse_hosted_clusters_path
from wingman_day1.domain.placement import (
    Admission,
    Choice,
    Decision,
    McePicture,
    Placement,
    PlacementInputs,
    admit,
    place,
)
from wingman_day1.domain.servers import ServerRow
from wingman_day1.ports import HubApi, RepoReads, ServerInventory

MAX_OWNERS: Final = 4096
"""Owners kept, by file content; a production repo has a few hundred cluster files."""
SERVER_SCAN_OFF: Final = (
    "server-scan is not configured (SERVER_SCAN_URL), so spare servers are unknown."
)

MAX_REPLICAS: Final = 1000
"""The most replicas one need may ask for; more is a typing slip, not a cluster."""
TEMPLATE_REPLICAS: Final = 2
"""What the cluster template writes for a nodepool without replicas (``| default(2)``)."""

Record = Callable[[Decision], None]
Need = tuple[str, int]


@dataclass(frozen=True, slots=True)
class OpenCreate:
    """An open Wingman merge request that creates a cluster: where, and whose."""

    ref: ClusterRef
    owner: str | None


def added_text(diff: FileDiff) -> str:
    """A new file's text from its unified diff: every added line, without its ``+``."""
    lines = [
        line[1:]
        for line in diff.diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    return "\n".join(lines) + "\n"


def mador_of(content: str) -> str | None:
    """A cluster file's ``owner.mador``, as text; ``None`` when absent or unreadable."""
    try:
        owner = read_values(load_values(content)).owner
    except InvalidClusterFileError:
        return None
    mador = owner.get("mador") if owner else None
    if mador is None:
        return None
    return str(mador).strip() or None


def need_problems(needs: Sequence[Need]) -> list[str]:
    """Why a need is not a node type (a DNS label) with 1 to ``MAX_REPLICAS`` replicas."""
    problems: list[str] = []
    for infra_env, replicas in needs:
        problems += [f"need: {p}" for p in dns_label_problems(infra_env, what="InfraEnv")]
        if not 1 <= replicas <= MAX_REPLICAS:
            problems.append(
                f"need: {infra_env} asks for {replicas} replicas; give 1 to {MAX_REPLICAS}"
            )
    return problems


def file_needs(content: str) -> list[Need]:
    """A cluster file's needs: each ``nodepool[]`` entry's ``infraEnvName`` and ``replicas``."""
    try:
        pools = read_values(load_values(content)).nodepools
    except InvalidClusterFileError:
        return []
    return [
        (pool.infra_env_name, pool.replicas)
        for pool in pools
        if pool.infra_env_name and pool.replicas is not None
    ]


def preset_needs(nodepools: object, ratio: Sequence[int]) -> list[Need]:
    """A flavor's needs: its preset nodepools that name an InfraEnv, with their replicas.

    A nodepool without preset replicas gets its ratio's part (at size 1), else
    what the template writes.
    """
    if not isinstance(nodepools, list):
        return []
    needs: list[Need] = []
    for index, pool in enumerate(nodepools):
        infra_env = pool.get("infra_env") if isinstance(pool, dict) else None
        if not isinstance(infra_env, str) or not infra_env.strip():
            continue
        replicas = pool.get("replicas")
        if isinstance(replicas, bool) or not isinstance(replicas, int) or replicas < 1:
            replicas = ratio[index] if index < len(ratio) else TEMPLATE_REPLICAS
        needs.append((infra_env.strip(), replicas))
    return needs


def owner_problems_of(owner: str | None) -> list[str]:
    """Why ``owner`` is not a mador number (ADR-0028); empty when it is, or is absent."""
    if owner is None or (owner.isascii() and owner.isdigit() and len(owner) <= MAX_OWNER_DIGITS):
        return []
    return [f"owner: must be a mador number of 1 to {MAX_OWNER_DIGITS} digits (got {owner!r})"]


class PlacementService:
    """Reads what the placement rule needs, and checks a create's choice against it."""

    def __init__(
        self,
        day1: RepoReads,
        sites: SiteCatalog,
        hub: HubApi | None,
        *,
        inventory: ServerInventory | None,
        min_free_pods: int,
        specs: SpecCatalog | None = None,
        infraenv_namespace: str | None = None,
        scan_names: Mapping[str, str] | None = None,
        record: Record | None = None,
    ) -> None:
        """``hub`` should be cached for seconds only; ``inventory`` is server-scan, if configured.

        ``hub`` is ``None`` when live MCE reads are off: placement then decides
        on the day1 repo and server-scan, and says what it did not check.

        ``specs`` gives a flavor's preset nodepools when the form sends no
        needs. ``infraenv_namespace`` (``MCE_INFRAENV_NAMESPACE``) is where the
        Agents are listed; ``None`` lists them across the hub. ``scan_names``
        maps a day1 MCE folder to the name server-scan gives it, where they
        differ (none do yet: they are matched exactly). ``record`` counts each
        create's decision (the metric).
        """
        self._day1 = day1
        self._sites = sites
        self._hub = hub
        self._inventory = inventory
        self._min_free_pods = min_free_pods
        self._specs = specs
        self._infraenv_namespace = infraenv_namespace or None
        self._scan_names = dict(scan_names or {})
        self._record = record
        self._owners: OrderedDict[bytes, str | None] = OrderedDict()

    @property
    def min_free_pods(self) -> int:
        """``PLACEMENT_MIN_FREE_PODS``."""
        return self._min_free_pods

    async def place(
        self,
        *,
        site: str,
        env: Env,
        version: str | None = None,
        owner: str | None = None,
        flavor: str | None = None,
        needs: Sequence[Need] | None = None,
    ) -> Placement:
        """Every candidate at ``site`` for ``env``, checked and ranked, and the pick.

        ``needs`` are the nodepools' ``(InfraEnv, replicas)``; ``None`` takes
        the flavor's presets. An unknown site or flavor is
        ``ResourceNotFoundError``; a version that is not a release, an owner
        that is not a mador number, or a need that is not a node type with 1
        to 1000 replicas, is ``InvalidInputError``.
        """
        problems = owner_problems_of(owner)
        if version is not None and not is_release(version):
            problems.append(f"version: {version!r} is not an OpenShift release like 4.18.22")
        problems += need_problems(needs or [])
        if problems:
            raise InvalidInputError("the placement's inputs are not acceptable", problems)
        if needs is None:
            needs = await self._flavor_needs(flavor)
        names = await self._sites.mce_names(site)
        candidates = [m for m in names if describe_mce(m, site=site).env is env]
        inputs = PlacementInputs(
            site=site,
            env=env,
            version=bare_release(version) if version is not None else None,
            owner=owner,
            flavor=flavor,
            min_free_pods=self._min_free_pods,
            needs=summed_needs(needs),
        )
        tree, (opens, open_problems), (rows, scan_error) = await asyncio.gather(
            read_tree(self._day1), self._open_creates(), self._fleet()
        )
        pictures = await asyncio.gather(
            *(
                self._picture(mce, inputs, tree=tree, opens=opens, rows=rows, scan_error=scan_error)
                for mce in candidates
            )
        )
        return place(
            inputs,
            pictures,
            problems=open_problems,
            server_scan_error=scan_error,
            live_reads=self._hub is not None,
        )

    async def admit(
        self, ref: ClusterRef, content: str, choice: Choice | None, *, flavor: str
    ) -> Admission:
        """Check a new cluster file's MCE against the rule, for its own version and owner.

        Raises ``InvalidInputError`` (422) for an MCE that fails a check, or an
        override without a reason, and ``PlacementChangedError`` (409) when the
        form's pick is no longer the pick.
        """
        values = load_values(content)
        env = describe_mce(ref.mce, site=ref.site).env
        if env is None:
            raise InvalidInputError(
                f"MCE {ref.mce!r} does not follow ocp4-<env>-mce-{ref.site}-<letter>, so it is "
                "never a placement candidate"
            )
        version = str(values.get("mastertag") or "").strip() or None
        placement = await self.place(
            site=ref.site,
            env=env,
            version=version if version and is_release(version) else None,
            owner=mador_of(content),
            flavor=flavor,
            needs=[n for n in file_needs(content) if not need_problems([n])],
        )
        return admit(placement, ref.mce, choice)

    def record(self, decision: Decision) -> None:
        """Count a create's decision (``wingman_placement_decisions_total``)."""
        if self._record is not None:
            self._record(decision)

    # ── Reads ───────────────────────────────────────────────────────────────

    async def _picture(
        self,
        mce: str,
        inputs: PlacementInputs,
        *,
        tree: Day1Tree,
        opens: Sequence[OpenCreate],
        rows: Sequence[ServerRow] | None,
        scan_error: str | None,
    ) -> McePicture:
        files = [ref for ref in tree.clusters if (ref.site, ref.mce) == (inputs.site, mce)]
        here = [o for o in opens if (o.ref.site, o.ref.mce) == (inputs.site, mce)]
        versions, owners, (pods, hub_error), (agents, agents_error) = await asyncio.gather(
            self._sites.openshift_versions(mce),
            asyncio.gather(*(self._owner_of(ref) for ref in files)),
            self._free_pods(mce),
            self._agents(mce, inputs.needs),
        )
        owner_clusters = None
        if inputs.owner is not None:
            every = [*owners, *(o.owner for o in here)]
            owner_clusters = sum(1 for found in every if found == inputs.owner)
        spare, spare_detail = None, scan_error
        if rows is not None:
            spare = spare_servers(rows, self._scan_names.get(mce, mce))
            if spare is None:
                spare_detail = (
                    f"server-scan names no server for {mce}, so its spare servers are unknown."
                )
        return McePicture(
            mce=mce,
            versions=versions,
            clusters=len(files) + len(here),
            open_creates=len(here),
            owner_clusters=owner_clusters,
            spare=spare,
            spare_detail=spare_detail,
            pods=pods,
            hub_error=hub_error,
            node_types=(
                node_type_supply(
                    inputs.needs, agents, rows, server_scan=self._inventory is not None
                )
                if self._hub is not None
                else ()
            ),
            agents_error=agents_error,
            live=self._hub is not None,
        )

    async def _flavor_needs(self, flavor: str | None) -> list[Need]:
        """The flavor's preset nodepools that name an InfraEnv; none without a flavor."""
        if flavor is None or self._specs is None:
            return []
        spec = await self._specs.get(flavor)
        needs = preset_needs(spec.presets().get("nodepools"), spec.sizing_ratio())
        return [n for n in needs if not need_problems([n])]

    async def _agents(
        self, mce: str, needs: Sequence[Need]
    ) -> tuple[list[AgentObservation] | None, str | None]:
        """The MCE's Agents of the needed InfraEnvs, or why they could not be read."""
        if not needs or self._hub is None:
            return [], None
        try:
            agents = await self._hub.infra_env_agents(
                mce,
                infra_envs=[infra_env for infra_env, _ in needs],
                namespace=self._infraenv_namespace,
            )
        except HubNotConfiguredError:
            return None, f"Wingman has no token for {mce} (MCE_TOKENS_FILE)."
        except HubDeniedError as exc:
            return None, f"Its token may not list Agents ({exc})."
        except HubError as exc:
            return None, f"Its Agents could not be read: {exc}."
        return agents, None

    async def _free_pods(self, mce: str) -> tuple[FreePods | None, str | None]:
        """The MCE's free pods, or why its nodes and pods could not be read."""
        if self._hub is None:
            return None, None
        try:
            nodes, pods = await asyncio.gather(self._hub.nodes(mce), self._hub.pods_per_node(mce))
        except HubNotConfiguredError:
            return None, f"Wingman has no token for {mce} (MCE_TOKENS_FILE)."
        except HubDeniedError as exc:
            return None, f"its token may not list nodes and pods ({exc})."
        except HubError as exc:
            return None, f"{exc}."
        return free_pods(nodes, pods), None

    async def _owner_of(self, ref: ClusterRef) -> str | None:
        try:
            content = (await self._day1.read(ref.path)).content
        except NotFoundError:
            return None  # removed between the tree listing and the read
        return self._mador(content)

    def _mador(self, content: str) -> str | None:
        """The file's mador, parsed once per distinct text."""
        key = hashlib.sha256(content.encode()).digest()
        if key in self._owners:
            self._owners.move_to_end(key)
            return self._owners[key]
        found = self._owners[key] = mador_of(content)
        if len(self._owners) > MAX_OWNERS:
            self._owners.popitem(last=False)
        return found

    async def _open_creates(self) -> tuple[list[OpenCreate], list[str]]:
        """Every open Wingman MR that creates a cluster, where its file goes, and whose it is."""
        opened = await self._day1.merge_requests(state=MRState.OPENED, labels=(WINGMAN_LABEL,))
        creates = [mr for mr in opened if _creates_a_cluster(mr)]
        found = await asyncio.gather(*(self._open_create(mr) for mr in creates))
        return (
            [o for o, _ in found if o is not None],
            [problem for _, problem in found if problem is not None],
        )

    async def _open_create(self, mr: MergeRequest) -> tuple[OpenCreate | None, str | None]:
        try:
            diffs = await self._day1.merge_request_diff(mr)
        except GitError as exc:
            return (
                None,
                f"Open merge request {mr.web_url} could not be read, so it is not counted: {exc}",
            )
        for diff in diffs:
            entry = parse_hosted_clusters_path(diff.new_path) if diff.new_file else None
            if entry is not None and entry.cluster is not None:
                return OpenCreate(entry.cluster, self._mador(added_text(diff))), None
        return None, (
            f"Open merge request {mr.web_url} adds no cluster file yet (GitLab may still be "
            "computing its diff), so it is not counted."
        )

    async def _fleet(self) -> tuple[list[ServerRow] | None, str | None]:
        if self._inventory is None:
            return None, SERVER_SCAN_OFF
        try:
            return await self._inventory.rows(), None
        except ServerScanUnavailableError as exc:
            return None, f"server-scan could not be read, so spare servers are unknown: {exc}"


def _creates_a_cluster(mr: MergeRequest) -> bool:
    title = parse_mr_title(mr.title)
    return title is not None and (title.repo, title.verb, title.resource_type) == (
        Repo.DAY1,
        Verb.CREATE,
        ResourceType.CLUSTER,
    )
