"""The bodies of ``/api/day2`` add-on authoring (ADR-0043, ADR-0053): plans and their MRs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wingman_day2.api.v1.schemas import (
    FileChangeOut,
    FindingOut,
    MRDetailOut,
    SyncOut,
    _Input,
    findings,
)
from wingman_day2.application.authoring import (
    SCOPE_LABELS,
    AddonTemplate,
    Adoption,
    AuthoringPlan,
    AuthoringResult,
    DestinationImpact,
    FleetDefault,
    KeyChange,
    NewAddon,
    TeamDefaultEdit,
)
from wingman_day2.application.changes import MceInstall, MceInstalls
from wingman_day2.domain.clusters import DefaultsScope
from wingman_day2.domain.deploy_config import (
    IGNORE_DIFFERENCES,
    PATH,
    PROJECT_NAMESPACE,
    REPOURL,
    TARGET_REVISION,
)
from wingman_day2.domain.sync_policy import KNOWN_SYNC_OPTIONS, SyncSettings

# ── Requests ────────────────────────────────────────────────────────────────


class SyncIn(_Input):
    """A leaf app's sync options (ADR-0043)."""

    auto_sync: bool = False
    prune: bool = Field(default=False, description="Only with auto_sync.")
    self_heal: bool = Field(default=False, description="Only with auto_sync.")
    sync_options: list[str] = Field(default_factory=list, description="Name=value, in order.")

    def settings(self) -> SyncSettings:
        """The domain settings (checked where they are used)."""
        return SyncSettings(self.auto_sync, self.prune, self.self_heal, tuple(self.sync_options))


class CreateAddonBody(_Input):
    """A new add-on in a team's catalog (``operators/<name>/``), optionally a fleet default."""

    name: str
    repourl: str
    target_revision: str | None = Field(default=None, description="A chart repo branch; HEAD.")
    path: str | None = None
    project_namespace: str | None = None
    sync: SyncIn
    ignore_differences: list[dict[str, Any]] | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    default_scope: DefaultsScope | None = None
    default_values: dict[str, Any] = Field(default_factory=dict)
    confirm_changes: list[str] = Field(default_factory=list)
    expected_digest: str | None = Field(default=None, description="The preview's digest.")
    message: str | None = None

    def spec(self, team: str) -> NewAddon:
        """The application's request."""
        return NewAddon(
            team=team,
            chart=self.name,
            repourl=self.repourl,
            sync=self.sync.settings(),
            target_revision=self.target_revision,
            path=self.path,
            project_namespace=self.project_namespace,
            ignore_differences=list(self.ignore_differences) if self.ignore_differences else None,
            values=self.values,
            default_scope=self.default_scope,
            default_values=self.default_values,
            confirm_changes=tuple(self.confirm_changes),
        )


_DEPLOY_KEYS = {
    "repourl": REPOURL,
    "target_revision": TARGET_REVISION,
    "path": PATH,
    "project_namespace": PROJECT_NAMESPACE,
    "ignore_differences": IGNORE_DIFFERENCES,
}


class UpdateTeamDefaultBody(_Input):
    """An edit of ``operators/<addon>/``: absent fields are unchanged, ``null`` removes a key."""

    repourl: str | None = None
    target_revision: str | None = None
    path: str | None = None
    project_namespace: str | None = None
    sync: SyncIn | None = Field(default=None, description="Absent or null: unchanged.")
    ignore_differences: list[dict[str, Any]] | None = None
    values: dict[str, Any] | None = Field(default=None, description="Absent or null: unchanged.")
    last_commit_id: str | None = None
    confirm_changes: list[str] = Field(default_factory=list)
    expected_digest: str | None = Field(default=None, description="The preview's digest.")
    message: str | None = None

    def edit(self) -> TeamDefaultEdit:
        """The application's request: only the fields the body sent."""
        sent = self.model_fields_set
        return TeamDefaultEdit(
            keys={
                key: getattr(self, field) for field, key in _DEPLOY_KEYS.items() if field in sent
            },
            sync=self.sync.settings() if self.sync is not None else None,
            values=self.values,
            last_commit_id=self.last_commit_id,
        )


class MakeDefaultBody(_Input):
    """Make an add-on a fleet default."""

    values: dict[str, Any] = Field(default_factory=dict)
    sync: SyncIn | None = Field(default=None, description="null: the team default's.")
    confirm_changes: list[str] = Field(default_factory=list)
    expected_digest: str | None = Field(default=None, description="The preview's digest.")
    message: str | None = None


class UpdateFleetDefaultBody(_Input):
    """An edit of ``defaults/<scope>/<addon>/``: absent fields are unchanged."""

    values: dict[str, Any] | None = None
    sync: SyncIn | None = Field(default=None, description="null: back to the team default's.")
    last_commit_id: str | None = None
    confirm_changes: list[str] = Field(default_factory=list)
    expected_digest: str | None = Field(default=None, description="The preview's digest.")
    message: str | None = None


class _Confirmed(_Input):
    last_commit_id: str | None = Field(default=None, description="The file's, as read.")
    confirm_changes: list[str] = Field(default_factory=list)
    expected_digest: str | None = Field(default=None, description="The preview's digest.")
    message: str | None = None


class DestinationValuesBody(_Confirmed):
    """A destination's ``values-<name>.yaml`` of a fleet default; null or {} deletes it."""

    values: dict[str, Any] | None


class MceInstallsBody(_Input):
    """Deploy an add-on on specific MCEs: one MR per MCE, in each one's own folder."""

    clusters: list[str] = Field(min_length=1, description="MCE ids, mce:<site>:<env>:<mce>.")
    values: dict[str, Any] = Field(default_factory=dict, description="Each MCE's values.yaml.")
    message: str | None = None


# ── Responses ───────────────────────────────────────────────────────────────


class ScopeOut(BaseModel):
    """A fleet scope and the destinations a default there reaches today."""

    scope: str
    label: str
    destinations: list[str]


class AddonTemplateOut(BaseModel):
    """What a new add-on form starts from."""

    team: str
    writable: bool
    read_only_reason: str | None
    sync: SyncOut
    sync_source: str
    repourl_prefix: str | None
    known_sync_options: list[str]
    scopes: list[ScopeOut]

    @classmethod
    def of(cls, template: AddonTemplate) -> AddonTemplateOut:
        """From the application value."""
        return cls(
            team=template.team,
            writable=template.access.writable,
            read_only_reason=template.access.reason,
            sync=SyncOut.of(template.sync),
            sync_source=template.sync_source,
            repourl_prefix=template.repourl_prefix,
            known_sync_options=list(KNOWN_SYNC_OPTIONS),
            scopes=[
                ScopeOut(
                    scope=str(s.scope),
                    label=s.label,
                    destinations=[ref.id for ref in s.destinations],
                )
                for s in template.scopes
            ],
        )


class FleetDefaultOut(BaseModel):
    """One ``defaults/<scope>/<chart>/`` of a team."""

    team: str
    chart: str
    scope: str
    scope_label: str
    path: str
    in_catalog: bool
    values: dict[str, Any]
    values_exists: bool
    sync: SyncOut
    sync_overridden: bool
    reach: list[str]
    excluded: list[str]
    tweaks: list[str]
    last_commit_id: str | None
    writable: bool
    read_only_reason: str | None
    warnings: list[FindingOut]

    @classmethod
    def of(cls, default: FleetDefault) -> FleetDefaultOut:
        """From the application value."""
        return cls(
            team=default.team,
            chart=default.chart,
            scope=str(default.scope),
            scope_label=SCOPE_LABELS[default.scope],
            path=str(default.folder),
            in_catalog=default.in_catalog,
            values=default.values.values,
            values_exists=default.values.exists,
            sync=SyncOut.of(default.sync),
            sync_overridden=default.sync_overridden,
            reach=[ref.id for ref in default.reach],
            excluded=[ref.id for ref in default.excluded],
            tweaks=[str(p) for p in default.tweaks],
            last_commit_id=default.last_commit_id,
            writable=default.access.writable,
            read_only_reason=default.access.reason,
            warnings=findings(default.findings),
        )


class PlannedFileOut(BaseModel):
    """One file a plan writes: its new text and its text before."""

    action: str
    path: str
    content: str | None
    previous: str | None


class KeyChangeOut(BaseModel):
    """One leaf of a destination's effective deploy config or values that changes.

    ``after_null``: a Helm ``null``, which deletes the key and the chart's own default.
    """

    stack: str
    key: str
    before: Any
    after: Any
    after_null: bool = False

    @classmethod
    def of(cls, change: KeyChange) -> KeyChangeOut:
        """From the application value."""
        return cls(
            stack=change.stack,
            key=change.key,
            before=change.before,
            after=change.after,
            after_null=change.after_null,
        )


class ImpactOut(BaseModel):
    """What an authoring MR does to one destination's app of the chart (ADR-0053)."""

    cluster: str
    name: str
    kind: str
    effect: str
    app_name: str
    changes: list[KeyChangeOut]
    orphaned: bool

    @classmethod
    def of(cls, impact: DestinationImpact) -> ImpactOut:
        """From the application value."""
        return cls(
            cluster=impact.ref.id,
            name=impact.ref.name,
            kind=str(impact.ref.kind),
            effect=str(impact.effect),
            app_name=impact.app_name,
            changes=[KeyChangeOut.of(c) for c in impact.changes],
            orphaned=impact.orphaned,
        )


class MovedOut(BaseModel):
    """A file moved into the fleet default."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(serialization_alias="from")
    to: str


class AdoptionOut(BaseModel):
    """A cluster whose own chart folder moves into the new fleet default."""

    cluster: str
    name: str
    moved: list[MovedOut]
    deleted: list[str]
    gitkeep: str | None
    changes: list[KeyChangeOut]
    exclusion_removed: bool

    @classmethod
    def of(cls, adoption: Adoption) -> AdoptionOut:
        """From the application value."""
        return cls(
            cluster=adoption.ref.id,
            name=adoption.ref.name,
            moved=[MovedOut(from_=str(a), to=str(b)) for a, b in adoption.moved],
            deleted=[str(p) for p in adoption.deleted],
            gitkeep=str(adoption.gitkeep) if adoption.gitkeep else None,
            changes=[KeyChangeOut.of(c) for c in adoption.changes],
            exclusion_removed=adoption.exclusion_removed,
        )


class _AuthoringFields(BaseModel):
    action: str
    chart: str
    scope: str | None
    reach: list[str]
    adopted: list[AdoptionOut]
    impact: list[ImpactOut]
    excluded: list[str]
    needs_confirmation: list[str]
    digest: str
    warnings: list[FindingOut]
    notes: list[str]

    @staticmethod
    def fields_of(plan: AuthoringPlan) -> dict[str, Any]:
        return {
            "action": str(plan.action),
            "chart": plan.chart,
            "scope": str(plan.scope) if plan.scope else None,
            "reach": [ref.id for ref in plan.reach],
            "adopted": [AdoptionOut.of(a) for a in plan.adopted],
            "impact": [ImpactOut.of(i) for i in plan.impact],
            "excluded": [ref.id for ref in plan.excluded],
            "needs_confirmation": plan.needs_confirmation,
            "digest": plan.digest,
            "warnings": findings(plan.findings),
            "notes": list(plan.notes),
        }


class AuthoringPlanOut(_AuthoringFields):
    """A dry run: what the MR would write and do; nothing was opened."""

    team: str
    title: str
    files: list[PlannedFileOut]

    @classmethod
    def of(cls, plan: AuthoringPlan) -> AuthoringPlanOut:
        """From the plan."""
        return cls(
            team=plan.team,
            title=plan.title,
            files=[
                PlannedFileOut(
                    action=str(c.kind),
                    path=str(c.path),
                    content=c.content,
                    previous=plan.previous.get(str(c.path)),
                )
                for c in plan.changes
            ],
            **cls.fields_of(plan),
        )


class AuthoringChangeOut(MRDetailOut, _AuthoringFields):
    """An opened authoring MR (an ``MRDetail``) plus what it writes and does."""

    files: list[FileChangeOut]

    @classmethod
    def of_result(cls, result: AuthoringResult) -> AuthoringChangeOut:
        """From the result of a real (not dry) run."""
        plan, merge_request = result.plan, result.merge_request
        if merge_request is None:
            raise ValueError("a dry run opened no merge request")
        base = MRDetailOut.of(plan.team, merge_request)
        return cls(
            **base.model_dump(),
            files=[FileChangeOut.of(c) for c in plan.changes],
            **_AuthoringFields.fields_of(plan),
        )


class MceInstallOut(BaseModel):
    """One chosen MCE of a deploy on specific MCEs."""

    cluster: str
    name: str
    status: str = Field(description="planned (a dry run), opened, refused or failed.")
    files: list[FileChangeOut]
    notes: list[str]
    warnings: list[FindingOut]
    merge_request: MRDetailOut | None
    detail: str | None = Field(description="Why it was refused or failed.")
    rule: str | None

    @classmethod
    def of(cls, team: str, install: MceInstall) -> MceInstallOut:
        """From the application value."""
        error = install.refused or install.failed
        rule = install.refused.details.get("rule") if install.refused is not None else None
        result = install.result
        return cls(
            cluster=install.cluster.id,
            name=install.cluster.name,
            status=install.status,
            files=[FileChangeOut.of(c) for c in install.changes],
            notes=list(result.notes if result else install.notes),
            warnings=findings(install.findings),
            merge_request=MRDetailOut.of(team, result.merge_request) if result else None,
            detail=(getattr(error, "detail", None) or str(error)) if error is not None else None,
            rule=str(rule) if rule is not None else None,
        )


class MceInstallsOut(BaseModel):
    """A deploy on specific MCEs: each chosen MCE, in the order asked."""

    team: str
    chart: str
    installs: list[MceInstallOut]

    @classmethod
    def of(cls, result: MceInstalls) -> MceInstallsOut:
        """From the application value."""
        return cls(
            team=result.team,
            chart=result.chart,
            installs=[MceInstallOut.of(result.team, i) for i in result.installs],
        )
