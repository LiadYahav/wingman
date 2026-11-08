"""Hosted clusters: list, show, preview, create, modify, delete.

Reads come from the day1 repo's default branch; changes go through the
``ClusterProvisioner`` (today a merge request, ADR-0017). A new cluster file
is rendered from the shared template, then checked against the values-file
contract before anything is written (ADR-0012), and its name against the
naming rules (ADR-0014). Its owners must be numbers (ADR-0028), its machine
configs must resolve by the day1 CI's rule, and the cluster's network config
entry is expanded to the name the CI reads before the template renders
(ADR-0027). A file that cannot be parsed is shown with its
error, never dropped from the list (ADR-0004).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import Commit, FileContent
from wingman_core.domain.merge_request import MRState
from wingman_core.domain.mr_conventions import Repo, ResourceType, Verb, parse_mr_title
from wingman_core.domain.users import User
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.application.tree import read_tree
from wingman_day1.domain.addons import RequestedAddon
from wingman_day1.domain.changes import ClusterAction, ClusterChange, ProvisionResult
from wingman_day1.domain.cluster_file import (
    ClusterValues,
    Provenance,
    describe_for_review,
    edit_problems,
    load_values,
    read_provenance,
    read_values,
    rendered_file_problems,
    require_valid,
    with_provenance,
)
from wingman_day1.domain.errors import (
    AlreadyInUseError,
    AmbiguousNameError,
    InvalidClusterFileError,
    InvalidInputError,
    RenderError,
    ResourceNotFoundError,
    StaleError,
)
from wingman_day1.domain.machine_configs import (
    MachineConfigCatalog,
    cluster_config_problems,
    expand_network_configs,
)
from wingman_day1.domain.names import (
    ClusterNaming,
    HostedClusterNaming,
    HostedClusterRef,
    describe_cluster,
    new_cluster_problems,
)
from wingman_day1.domain.owners import owner_problems
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.specs import ClusterSpec
from wingman_day1.domain.template import build_inputs, check_inputs, render_cluster_file
from wingman_day1.ports import ClusterProvisioner, RepoReads

MAX_LIST_CONCURRENCY = 16


@dataclass(frozen=True, slots=True)
class ClusterFile:
    """A cluster file at the default branch, read and interpreted."""

    ref: ClusterRef
    content: str
    last_commit_id: str
    naming: ClusterNaming
    hosted_cluster: HostedClusterRef
    provenance: Provenance
    values: ClusterValues | None
    """``None`` when the file does not parse; ``problems`` says why."""
    problems: tuple[str, ...] = ()
    last_change: Commit | None = None


@dataclass(frozen=True, slots=True)
class CreateCluster:
    """A request to create a cluster from a spec."""

    name: str
    site: str
    mce: str
    spec_name: str
    spec_version: str
    variables: Mapping[str, object] = field(default_factory=dict)
    addon_overrides: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    """Day2 override values per spec addon, keyed ``team/name``; kept in the file header."""


@dataclass(frozen=True, slots=True)
class RenderedCluster:
    """What a create would commit."""

    ref: ClusterRef
    content: str
    spec: ClusterSpec
    requested_addons: tuple[RequestedAddon, ...]


class ClusterService:
    """The cluster use cases."""

    def __init__(
        self,
        day1: RepoReads,
        sites: SiteCatalog,
        specs: SpecCatalog,
        provisioner: ClusterProvisioner,
        machine_configs: MachineConfigService,
        *,
        naming: HostedClusterNaming,
    ) -> None:
        """Read through ``day1`` (cached), write through ``provisioner``."""
        self._day1 = day1
        self._sites = sites
        self._specs = specs
        self._provisioner = provisioner
        self._machine_configs = machine_configs
        self._naming = naming

    # ── Reads ───────────────────────────────────────────────────────────────

    async def clusters(self) -> list[ClusterFile]:
        """Every cluster file under every MCE, including off-convention and unparsable ones."""
        tree = await read_tree(self._day1)
        limit = asyncio.Semaphore(MAX_LIST_CONCURRENCY)

        async def one(ref: ClusterRef) -> ClusterFile | None:
            async with limit:
                try:
                    return await self._load(ref, with_commit=True)
                except ResourceNotFoundError:
                    return None  # removed between the tree listing and the read

        loaded = await asyncio.gather(*(one(ref) for ref in tree.clusters))
        return [c for c in loaded if c is not None]

    async def locate(
        self, name: str, *, site: str | None = None, mce: str | None = None
    ) -> ClusterRef:
        """Where a cluster is. With ``site`` and ``mce`` it is taken as given."""
        if site and mce:
            return ClusterRef(site, mce, name)
        matches = [
            ref
            for ref in (await read_tree(self._day1)).find(name)
            if (site is None or ref.site == site) and (mce is None or ref.mce == mce)
        ]
        if not matches:
            raise ResourceNotFoundError(f"cluster {name!r} does not exist in the day1 repo")
        if len(matches) > 1:
            where = ", ".join(f"{r.site}/{r.mce}" for r in matches)
            raise AmbiguousNameError(f"cluster {name!r} exists under {where}; pass site and mce")
        return matches[0]

    async def get(self, ref: ClusterRef) -> ClusterFile:
        """One cluster file, with its last change."""
        return await self._load(ref, with_commit=True)

    async def history(self, ref: ClusterRef) -> list[Commit]:
        """Commits that changed the cluster's file, newest first."""
        return await self._day1.history(ref.path)

    async def web_url(self, ref: ClusterRef) -> str:
        """The file in GitLab's UI, at the default branch."""
        project = await self._day1.project()
        return f"{project.web_url}/-/blob/{project.default_branch}/{ref.path}"

    # ── Create ──────────────────────────────────────────────────────────────

    async def preview(self, request: CreateCluster) -> RenderedCluster:
        """Render and check a new cluster file without writing anything."""
        ref = ClusterRef(request.site, request.mce, request.name)
        await self._sites.require_mce(ref.site, ref.mce)
        problems = new_cluster_problems(ref.name, site=ref.site, mce=ref.mce, naming=self._naming)
        if problems:
            raise InvalidInputError(f"cluster name {ref.name!r} cannot be used", problems)
        await self._require_unused(ref)
        spec = await self._specs.get(request.spec_name)
        if spec.metadata.version != request.spec_version:
            raise StaleError(
                f"spec {request.spec_name} is now v{spec.metadata.version}, not "
                f"v{request.spec_version}; reload the form"
            )
        addons = spec.requested_addons(request.addon_overrides)
        catalog = await self._machine_configs.catalog()
        content = self._render(ref, spec, request.variables, catalog)
        provenance = Provenance(spec.metadata.name, spec.metadata.version, tuple(addons))
        return RenderedCluster(ref, with_provenance(content, provenance), spec, tuple(addons))

    async def create(self, request: CreateCluster, *, user: User) -> ProvisionResult:
        """Propose a new cluster: one new file, in one commit, in one MR."""
        rendered = await self.preview(request)
        values = read_values(load_values(rendered.content))
        addons = ", ".join(f"`{a.key}@{a.version}`" for a in rendered.requested_addons)
        summary = (
            f"Creating hosted cluster **{rendered.ref.name}** from spec "
            f"`{rendered.spec.metadata.name}` v{rendered.spec.metadata.version}.\n\n"
            f"Site `{rendered.ref.site}`, MCE `{rendered.ref.mce}`.\n\n"
            f"{describe_for_review(values)}\n\n"
            f"Day2 addons requested by the spec: {addons or 'none'}.\n\n"
            "After this branch is pushed, CI and the allocate-segment workflow add `vlanId`, "
            "`dhcp_values` and `mcConfigMap` to the file; merge once they have."
        )
        return await self._provisioner.apply(
            ClusterChange(
                action=ClusterAction.CREATE,
                cluster=rendered.ref,
                requested_by=user,
                summary=summary,
                content=rendered.content,
                spec_name=rendered.spec.metadata.name,
                spec_version=rendered.spec.metadata.version,
            )
        )

    # ── Modify and delete ───────────────────────────────────────────────────

    async def modify(
        self,
        ref: ClusterRef,
        content: str,
        *,
        user: User,
        summary: str,
        last_commit_id: str | None = None,
    ) -> ProvisionResult:
        """Propose a new content for an existing file, guarded by the revision it was read at."""
        current = await self._read(ref)
        expected = self._expect(ref, current, last_commit_id)
        if content == current.content:
            raise InvalidInputError("the edit changes nothing", ["the content is identical"])
        require_valid(edit_problems(current.content, content), message="the edit is not valid")
        return await self._provisioner.apply(
            ClusterChange(
                action=ClusterAction.MODIFY,
                cluster=ref,
                requested_by=user,
                summary=summary or f"Modify cluster {ref.name} via Wingman",
                content=content,
                last_commit_id=expected,
            )
        )

    async def delete(
        self, ref: ClusterRef, *, user: User, last_commit_id: str | None = None
    ) -> ProvisionResult:
        """Propose removing the cluster's file (its Application, and so the cluster, goes)."""
        current = await self._read(ref)
        expected = self._expect(ref, current, last_commit_id)
        return await self._provisioner.apply(
            ClusterChange(
                action=ClusterAction.DELETE,
                cluster=ref,
                requested_by=user,
                summary=(
                    f"Deleting hosted cluster **{ref.name}** (site `{ref.site}`, MCE "
                    f"`{ref.mce}`). Merging removes its Argo Application. Its VLAN segment is "
                    "released only where the chart's PostDelete hook exists."
                ),
                last_commit_id=expected,
            )
        )

    # ── Internals ───────────────────────────────────────────────────────────

    def _render(
        self,
        ref: ClusterRef,
        spec: ClusterSpec,
        variables: Mapping[str, object],
        catalog: MachineConfigCatalog,
    ) -> str:
        inputs = build_inputs(
            variables=variables,
            cluster_name=ref.name,
            site=ref.site,
            mce=ref.mce,
            openshift_release_version=None,
            presets=spec.presets(),
        )
        problems = check_inputs(inputs)
        if problems:
            raise InvalidInputError("the cluster's inputs are not acceptable", problems)
        cluster_name = self._naming.for_file(ref.name).cluster_name
        problems = owner_problems(inputs)
        problems += cluster_config_problems(inputs, catalog, cluster_name=cluster_name)
        if problems:
            raise InvalidInputError("the cluster's inputs are not acceptable", problems)
        inputs = expand_network_configs(inputs, cluster_name=cluster_name)
        template = spec.spec.day1.template
        if not template.strip():
            raise RenderError("the specs project has no cluster-template.j2")
        rendered = render_cluster_file(template, inputs)
        require_valid(
            rendered_file_problems(rendered),
            message="the rendered cluster file breaks the values-file contract",
        )
        return rendered

    async def _require_unused(self, ref: ClusterRef) -> None:
        """Cluster names are unique across the whole repo, and across open create MRs."""
        existing = (await read_tree(self._day1)).find(ref.name)
        if existing:
            where = existing[0]
            raise AlreadyInUseError(
                f"cluster {ref.name!r} already exists under {where.site}/{where.mce}"
            )
        for merge_request in await self._day1.merge_requests(
            state=MRState.OPENED, labels=("wingman",)
        ):
            title = parse_mr_title(merge_request.title)
            if (
                title is not None
                and (title.repo, title.verb, title.resource_type)
                == (Repo.DAY1, Verb.CREATE, ResourceType.CLUSTER)
                and title.resource_name == ref.name
            ):
                raise AlreadyInUseError(
                    f"an open merge request already creates cluster {ref.name!r}: "
                    f"{merge_request.web_url}"
                )

    async def _read(self, ref: ClusterRef) -> FileContent:
        try:
            return await self._day1.read(ref.path)
        except NotFoundError as exc:
            raise ResourceNotFoundError(
                f"cluster {ref.name!r} does not exist under {ref.site}/{ref.mce}"
            ) from exc

    @staticmethod
    def _expect(ref: ClusterRef, current: FileContent, expected: str | None) -> str:
        if expected is not None and expected != current.last_commit_id:
            raise StaleError(
                f"cluster {ref.name!r} changed since it was read ({expected[:8]} → "
                f"{current.last_commit_id[:8]}); reload and try again"
            )
        return expected or current.last_commit_id

    async def _load(self, ref: ClusterRef, *, with_commit: bool) -> ClusterFile:
        file = await self._read(ref)
        problems: list[str] = []
        values: ClusterValues | None = None
        try:
            values = read_values(load_values(file.content))
        except InvalidClusterFileError as exc:
            problems.extend(exc.problems or [str(exc)])
        provenance = read_provenance(file.content)
        problems.extend(provenance.problems)
        last_change = await self._day1.commit(file.last_commit_id) if with_commit else None
        explicit = values.cluster_name if values else None
        return ClusterFile(
            ref=ref,
            content=file.content,
            last_commit_id=file.last_commit_id,
            naming=describe_cluster(ref.name, site=ref.site),
            hosted_cluster=self._naming.for_file(ref.name, explicit=explicit),
            provenance=provenance,
            values=values,
            problems=tuple(problems),
            last_change=last_change,
        )
