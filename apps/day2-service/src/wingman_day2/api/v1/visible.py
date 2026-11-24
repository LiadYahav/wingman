"""The destination a route names, and each answer, as the user may know them (ADR-0068).

Every ``/api/day2/clusters/{cluster}...`` read and ``POST /merge-preview``
find their destination with :meth:`View.destination`: an admin's by id or
bare name (``mce`` narrows it), a viewer's by its bare name alone among the
tenants' clusters (``domain/visibility.py``); an id, ``hub`` or an MCE are an
admin's to send. The service is then asked by the destination's id, so it
never resolves the name again against what a viewer may not know of.

A viewer's answer goes through :meth:`View.shown`: a tenant's id reads as its
name and a path in its folder from the cluster on, the findings they may not
read are left out, the admin-only fields (``mce``, ``argo``, ``gitlab_url``)
are ``null`` and every text is redacted (``wingman_core.web.viewer``). Their
merge requests, commits and diffs are those about a tenant, their fleet
scope the hosted clusters', and their errors name nothing hidden either.
"""

from __future__ import annotations

from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import Commit, FileDiff
from wingman_core.domain.merge_request import MergeRequest
from wingman_core.domain.users import User
from wingman_core.web.viewer import for_viewer
from wingman_day2.api.v1.authoring_schemas import FleetDefaultOut
from wingman_day2.api.v1.operators_schemas import ExclusionsOut, OperatorOut
from wingman_day2.api.v1.schemas import CatalogEntryOut, FindingOut
from wingman_day2.application.audit import missing_commit
from wingman_day2.application.authoring import SCOPE_LABELS
from wingman_day2.application.services import Day2Services
from wingman_day2.application.topology import ClusterSummary, Topology, unknown_cluster
from wingman_day2.domain.clusters import HUB_ID, ClusterRef
from wingman_day2.domain.errors import AmbiguousClusterError, Day2Error
from wingman_day2.domain.visibility import VIEWER_SCOPE, Sight, real_path


class _Problem(BaseModel):
    """A day2 error's words, to read them as a viewer does."""

    detail: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class View:
    """What ``user`` may know of the topology, and how their answers read."""

    user: User
    topology: Topology
    sight: Sight

    @property
    def admin(self) -> bool:
        """Whether every answer is as it is."""
        return self.user.is_admin

    def destination(self, cluster: str, mce: str | None = None) -> ClusterSummary:
        """The destination ``cluster`` names; for a viewer, a tenant's cluster by its name alone.

        A viewer's ``mce`` is ignored, an id or ``hub`` from them is an unknown
        name, and a name two tenants' clusters share is ambiguous without
        their ids.
        """
        if self.admin:
            return self.topology.resolve(cluster, mce=mce)
        if cluster == HUB_ID or ":" in cluster:
            raise unknown_cluster(cluster)
        try:
            return self.topology.visible_to(self.user).resolve(cluster)
        except AmbiguousClusterError:
            raise AmbiguousClusterError(
                f"{cluster!r} names more than one cluster; ask an admin",
                details={"cluster": cluster},
            ) from None

    def repo_path(self, ref: ClusterRef, path: str | None) -> str | None:
        """The repo path a layer path the user sent stands for (a viewer's reads as shown)."""
        return path if self.admin or path is None else real_path(ref, path)

    def shown[M: BaseModel](self, model: M) -> M:
        """``model`` as the user reads it: a viewer's renamed, filtered and redacted."""
        if self.admin:
            return model
        return for_viewer(_renamed_model(model, self.sight), self.sight.redactor)

    def all_shown[M: BaseModel](self, models: Sequence[M]) -> list[M]:
        """:meth:`shown` of each that the user may read (a viewer reads some findings alone)."""
        return [self.shown(m) for m in models if self.admin or _readable(m, self.sight)]

    async def guarded[T](self, answer: Awaitable[T]) -> T:
        """``answer``; for a viewer, a day2 error it raises in words that name nothing hidden."""
        try:
            return await answer
        except Day2Error as exc:
            if self.admin:
                raise
            words = self.shown(_Problem(detail=exc.detail, details=exc.details))
            raise type(exc)(words.detail, details=words.details) from None

    def sees_merge_request(self, merge_request: MergeRequest) -> bool:
        """Whether the user may read the merge request: a viewer, one about a tenant."""
        return self.admin or self.sight.about(f"{merge_request.title}\n{merge_request.description}")

    def sees_commit(self, commit: Commit) -> bool:
        """Whether the user may read the commit: a viewer, one whose message is about a tenant."""
        return self.admin or self.sight.about(commit.message)

    def diffs(self, diffs: Sequence[FileDiff]) -> list[FileDiff]:
        """The files of a diff the user reads: a viewer's, a tenant's own and the team's own."""
        if self.admin:
            return list(diffs)
        readable = self.sight.file
        return [d for d in diffs if readable(str(d.old_path)) and readable(str(d.new_path))]

    def merge_request_diffs(
        self, merge_request: MergeRequest, diffs: Sequence[FileDiff]
    ) -> list[FileDiff]:
        """:meth:`diffs` of the merge request; a viewer's 404 when they may not read any of it."""
        shown = self.diffs(diffs)
        if not self.admin and not (shown and self.sees_merge_request(merge_request)):
            raise NotFoundError(f"merge request !{merge_request.ref.iid} not found")
        return shown

    def commit_diffs(self, sha: str, diffs: Sequence[FileDiff]) -> list[FileDiff]:
        """:meth:`diffs` of the commit; a viewer's 404 when no file of it is theirs to read."""
        shown = self.diffs(diffs)
        if not self.admin and not shown:
            raise missing_commit(sha)
        return shown

    def catalog(self, entry: CatalogEntryOut) -> CatalogEntryOut:
        """A catalog entry whose fleet defaults are those of the scopes the user may know of."""
        if self.admin:
            return entry
        scopes = [s for s in entry.fleet_defaults if s == VIEWER_SCOPE]
        return entry.model_copy(update={"fleet_defaults": scopes})

    def fleet_default(self, default: FleetDefaultOut) -> FleetDefaultOut | None:
        """A fleet default as the user may know of it; ``None`` for a viewer's of a hidden scope.

        A viewer's reaches and skips the tenants' clusters alone, and has the
        ``values-<name>.yaml`` of a tenant or an env alone.
        """
        if self.admin:
            return default
        if default.scope != VIEWER_SCOPE:
            return None
        names = self.sight.names
        return default.model_copy(
            update={
                "reach": [i for i in default.reach if i in names],
                "excluded": [i for i in default.excluded if i in names],
                "tweaks": [p for p in default.tweaks if self.sight.file(p) is not None],
            }
        )

    def addon(self, addon: OperatorOut) -> OperatorOut:
        """An add-on's page as the user may know of it.

        The service left a viewer the hosted clusters' scope and its tenants;
        here their scope lists no unregistered destination, and its
        ``exclusions.yaml`` the tenants' names alone.
        """
        if self.admin:
            return addon
        tenants = self.sight.tenant_names

        def exclusions(view: ExclusionsOut | None) -> ExclusionsOut | None:
            if view is None:
                return None
            names = [n for n in view.names if n in tenants]
            unknown = [n for n in view.unknown_names if n in tenants]
            return view.model_copy(update={"names": names, "unknown_names": unknown})

        scopes = [
            s.model_copy(update={"unregistered": [], "exclusions": exclusions(s.exclusions)})
            for s in addon.scopes
        ]
        catalog = self.catalog(addon.catalog) if addon.catalog else None
        return addon.model_copy(update={"scopes": scopes, "catalog": catalog})


async def view_of(day2: Day2Services, user: User) -> View:
    """``user``'s view of the topology, read once for the request."""
    topology = await day2.topology.load()
    return View(user, topology, Sight() if user.is_admin else topology.sight(SCOPE_LABELS))


def _readable(value: object, sight: Sight) -> bool:
    """Whether a viewer reads ``value``: every value but a finding about what is hidden."""
    return not isinstance(value, FindingOut) or sight.finding(value.cluster, value.path)


def _renamed_model[M: BaseModel](model: M, sight: Sight) -> M:
    fields = type(model).model_fields
    return model.model_copy(update={n: _renamed(getattr(model, n), sight) for n in fields})


def _renamed(value: object, sight: Sight) -> object:
    """``value`` with each tenant's id its name and each path in its folder from it, at any depth.

    A list leaves out the findings a viewer may not read.
    """
    match value:
        case Enum():
            return value
        case str():
            return sight.rename(value)
        case BaseModel():
            return _renamed_model(value, sight)
        case list():
            return [_renamed(v, sight) for v in value if _readable(v, sight)]
        case tuple():
            return tuple(_renamed(v, sight) for v in value)
        case dict():
            return {_renamed(k, sight): _renamed(v, sight) for k, v in value.items()}
        case _:
            return value
