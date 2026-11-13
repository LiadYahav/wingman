"""The bodies of ``/api/day2`` add-ons with their defaults (ADR-0053): one add-on, a team's list."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from wingman_day2.api.v1.schemas import CatalogEntryOut, FindingOut, SyncOut, findings
from wingman_day2.application.apps import LoadedLayer
from wingman_day2.application.authoring import SCOPE_LABELS, SCOPE_NOUNS
from wingman_day2.application.operators import (
    DestinationView,
    ExclusionsView,
    OcpVersionPin,
    OperatorSummary,
    OperatorView,
    ScopeView,
)
from wingman_day2.domain.deploy_config import SYNC_POLICY
from wingman_day2.domain.sync_policy import SyncSettings, sync_settings


class FileOut(BaseModel):
    """A file of the team repo; ``last_commit_id`` is the commit it was read at (null: absent)."""

    path: str
    exists: bool
    text: str | None
    values: dict[str, Any]
    last_commit_id: str | None
    problem: str | None

    @classmethod
    def of(cls, loaded: LoadedLayer) -> FileOut:
        """From a loaded file."""
        return cls(
            path=str(loaded.layer.path),
            exists=loaded.exists,
            text=loaded.file.content if loaded.file else None,
            values=loaded.values,
            last_commit_id=loaded.file.last_commit_id if loaded.file else None,
            problem=loaded.problem.message if loaded.problem else None,
        )


class OcpVersionOut(BaseModel):
    """An ``ocp-versions/<v>/`` pin of an add-on."""

    version: str
    target_revision: str | None
    deploy_config: FileOut
    values_file: FileOut

    @classmethod
    def of(cls, pin: OcpVersionPin) -> OcpVersionOut:
        """From the application value."""
        return cls(
            version=pin.version,
            target_revision=pin.target_revision,
            deploy_config=FileOut.of(pin.deploy),
            values_file=FileOut.of(pin.values),
        )


class ExclusionsOut(BaseModel):
    """A scope's ``exclusions.yaml`` for one add-on, read-only: Wingman never writes it."""

    path: str
    exists: bool
    names: list[str]
    unknown_names: list[str]
    last_commit_id: str | None

    @classmethod
    def of(cls, view: ExclusionsView) -> ExclusionsOut:
        """From the application value."""
        file = view.file.file
        return cls(
            path=str(view.file.layer.path),
            exists=view.file.exists,
            names=list(view.names),
            unknown_names=list(view.unknown_names),
            last_commit_id=file.last_commit_id if file else None,
        )


class ScopeDestinationOut(BaseModel):
    """One destination of a scope and how the add-on's default stands there."""

    id: str
    name: str
    kind: str
    site: str
    env: str
    mce: str
    ocp_version: str | None
    renders: bool
    state: str
    deployed: bool
    app_name: str | None
    override: FileOut | None
    override_shared_with: list[str]
    own_folder: str | None
    own_deploy: FileOut | None

    @classmethod
    def of(cls, view: DestinationView) -> ScopeDestinationOut:
        """From the application value."""
        ref = view.ref
        return cls(
            id=ref.id,
            name=ref.name,
            kind=str(ref.kind),
            site=ref.site,
            env=ref.env,
            mce=ref.mce,
            ocp_version=view.ocp_version,
            renders=view.renders,
            state=str(view.state),
            deployed=view.deployed,
            app_name=view.app_name,
            override=FileOut.of(view.override) if view.override else None,
            override_shared_with=[r.id for r in view.shared_with],
            own_folder=str(view.own_folder) if view.own_folder else None,
            own_deploy=FileOut.of(view.own_deploy) if view.own_deploy else None,
        )


class UnregisteredOut(BaseModel):
    """A destination of the scope that day1 or another team knows, and this team does not."""

    id: str
    name: str
    site: str
    env: str
    mce: str


class EnvFileOut(BaseModel):
    """A fleet default's ``values-<env>.yaml``."""

    env: str
    file: FileOut


class ScopePanelOut(BaseModel):
    """One scope of an add-on: its default there, if any, and every destination."""

    scope: str
    label: str
    noun: str
    is_default: bool
    folder: str
    values_file: FileOut
    deploy_config: FileOut
    sync: SyncOut
    sync_overridden: bool
    env_files: list[EnvFileOut]
    exclusions: ExclusionsOut | None
    destinations: list[ScopeDestinationOut]
    unregistered: list[UnregisteredOut]
    last_commit_id: str | None

    @classmethod
    def of(cls, view: ScopeView) -> ScopePanelOut:
        """From the application value."""
        return cls(
            scope=str(view.scope),
            label=SCOPE_LABELS[view.scope],
            noun=SCOPE_NOUNS[view.scope],
            is_default=view.is_default,
            folder=str(view.folder),
            values_file=FileOut.of(view.values),
            deploy_config=FileOut.of(view.deploy),
            sync=SyncOut.of(view.sync),
            sync_overridden=view.sync_overridden,
            env_files=[EnvFileOut(env=env, file=FileOut.of(f)) for env, f in view.env_files],
            exclusions=ExclusionsOut.of(view.exclusions) if view.exclusions else None,
            destinations=[ScopeDestinationOut.of(d) for d in view.destinations],
            unregistered=[
                UnregisteredOut(id=r.id, name=r.name, site=r.site, env=r.env, mce=r.mce)
                for r in view.unregistered
            ],
            last_commit_id=view.last_commit_id,
        )


class OperatorOut(BaseModel):
    """One add-on of a team: its files, its OCP-version pins, one panel per scope."""

    team: str
    name: str
    in_catalog: bool
    writable: bool
    read_only_reason: str | None
    catalog: CatalogEntryOut | None
    deploy_config: FileOut
    values_file: FileOut
    ocp_versions: list[OcpVersionOut]
    scopes: list[ScopePanelOut]
    warnings: list[FindingOut]

    @classmethod
    def of(cls, view: OperatorView) -> OperatorOut:
        """From the application value."""
        return cls(
            team=view.team,
            name=view.chart,
            in_catalog=view.in_catalog,
            writable=view.access.writable,
            read_only_reason=view.access.reason,
            catalog=CatalogEntryOut.of(view.catalog, view.access) if view.catalog else None,
            deploy_config=FileOut.of(view.deploy),
            values_file=FileOut.of(view.values),
            ocp_versions=[OcpVersionOut.of(p) for p in view.ocp_versions],
            scopes=[ScopePanelOut.of(s) for s in view.scopes],
            warnings=findings(view.findings),
        )


class OperatorDefaultOut(BaseModel):
    """A scope an add-on is a default on, and its reach there."""

    scope: str
    label: str
    reach: int
    excluded: int


class OperatorSummaryOut(BaseModel):
    """One line of a team's add-ons list."""

    team: str
    name: str
    in_catalog: bool
    repourl: str
    target_revision: str
    sync: SyncOut
    ocp_versions: list[str]
    defaults: list[OperatorDefaultOut]
    installed_on: int
    warnings: int
    writable: bool
    read_only_reason: str | None

    @classmethod
    def of(cls, summary: OperatorSummary) -> OperatorSummaryOut:
        """From the application value."""
        entry = summary.catalog
        sync = sync_settings(entry.deploy.values.get(SYNC_POLICY)) if entry else SyncSettings()
        return cls(
            team=summary.team,
            name=summary.chart,
            in_catalog=entry is not None,
            repourl=entry.repo_url if entry else "",
            target_revision=entry.team_revision if entry else "",
            sync=SyncOut.of(sync),
            ocp_versions=list(summary.ocp_versions),
            defaults=[
                OperatorDefaultOut(
                    scope=str(d.scope),
                    label=SCOPE_LABELS[d.scope],
                    reach=d.reach,
                    excluded=d.excluded,
                )
                for d in summary.defaults
            ],
            installed_on=summary.installed_on,
            warnings=summary.warnings,
            writable=summary.access.writable,
            read_only_reason=summary.access.reason,
        )
