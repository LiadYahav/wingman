"""Upgrading a hosted cluster through the platform's upgrade-cluster workflow (ADR-0055).

The workflow plans the path, checks it, waits for an approval and commits
the versions to day1 ``main`` itself. Wingman reads its targets, starts a
run, shows it and passes on a person's decisions; the run's validators
judge every decision, and a refusal is shown in their words. Day1 checks
only what makes a request well-formed for the workflow (a reason where it
requires one, a NodePool only for ``continue``) and that the cluster is in
the day1 repo. Who asked is the signed-in user, never the request, and day1
logs who did what. Nothing is retried (ADR-0006).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass

from wingman_core.domain.users import User
from wingman_day1.application.clusters import ClusterService
from wingman_day1.domain.errors import (
    AmbiguousDecisionError,
    AmbiguousStartError,
    InvalidInputError,
    ResourceNotFoundError,
    WorkflowsError,
)
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.upgrades import (
    UpgradeDecision,
    UpgradeRequest,
    UpgradeRun,
    UpgradeTargets,
    upgrade_workflow_id,
)
from wingman_day1.ports import UpgradeWorkflow

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StartUpgrade:
    """What the person chose in the Upgrade dialog; ``None`` leaves the workflow's default."""

    target_version: str | None = None
    target_minor: str | None = None
    nodepool_order: tuple[str, ...] | None = None
    max_unavailable: Mapping[str, int | str] | None = None
    workers_to_target: bool | None = None
    nodepool_mode: str | None = None
    auto_approve: bool | None = None


@dataclass(frozen=True, slots=True)
class Decided:
    """A decision the run took, and the run read again (``None`` when it could not be)."""

    workflow_id: str
    decision: str
    run: UpgradeRun | None


class UpgradeService:
    """Targets, start, run and decisions of one cluster's upgrade."""

    def __init__(self, workflow: UpgradeWorkflow, clusters: ClusterService) -> None:
        """Talk to the workflow; ``clusters`` says whether the day1 repo has the cluster."""
        self._workflow = workflow
        self._clusters = clusters

    async def targets(self, ref: ClusterRef) -> UpgradeTargets:
        """What the workflow offers to upgrade the cluster to (an empty list is an answer)."""
        await self._require(ref)
        return await self._workflow.targets(ref.name)

    async def start(self, ref: ClusterRef, choice: StartUpgrade, *, user: User) -> UpgradeRun:
        """Start an upgrade: the run plans, checks and waits for approval. Never retried."""
        await self._require(ref)
        if (choice.target_version is None) == (choice.target_minor is None):
            raise InvalidInputError(
                "choose one target", ["send exactly one of target_version and target_minor"]
            )
        request = UpgradeRequest(
            cluster=ref.name,
            requested_by=user.username,
            target_version=choice.target_version,
            target_minor=choice.target_minor,
            nodepool_order=choice.nodepool_order,
            max_unavailable=choice.max_unavailable,
            workers_to_target=choice.workers_to_target,
            nodepool_mode=choice.nodepool_mode,
            auto_approve=choice.auto_approve,
        )
        event = {**_where(ref, user), "target": request.target}
        try:
            run = await self._workflow.start(request)
        except AmbiguousStartError:
            _log(logging.WARNING, "upgrade start unconfirmed", "upgrade_start_unconfirmed", event)
            raise
        _log(logging.INFO, "upgrade started", "upgrade_started", {**event, "run": run.workflow_id})
        return run

    async def run(self, ref: ClusterRef) -> UpgradeRun:
        """The cluster's newest upgrade run; ``ResourceNotFoundError`` when it never had one."""
        await self._require(ref)
        run = await self._workflow.run(upgrade_workflow_id(ref.name))
        if run is None:
            raise ResourceNotFoundError(f"cluster {ref.name!r} has no upgrade run")
        return run

    async def decide(
        self,
        ref: ClusterRef,
        decision: UpgradeDecision,
        *,
        user: User,
        reason: str | None = None,
        nodepool: str | None = None,
    ) -> Decided:
        """Send one decision on the cluster's run, then read the run again."""
        _check(decision, reason=reason, nodepool=nodepool)
        await self._require(ref)
        workflow_id = upgrade_workflow_id(ref.name)
        event = {**_where(ref, user), "decision": decision.value, "run": workflow_id}
        if reason:
            event["reason"] = reason
        if nodepool:
            event["nodepool"] = nodepool
        await self._send(
            self._workflow.decide(
                workflow_id, decision, by=user.username, reason=reason, nodepool=nodepool
            ),
            event,
        )
        return Decided(workflow_id, decision.value, await self._reread(workflow_id))

    async def decide_action(
        self, ref: ClusterRef, action_id: str, *, approve: bool, user: User
    ) -> Decided:
        """Approve or reject one of the upgrade agent's proposals, then read the run again."""
        await self._require(ref)
        workflow_id = upgrade_workflow_id(ref.name)
        decision = "approve-action" if approve else "reject-action"
        event = {
            **_where(ref, user),
            "decision": decision,
            "action": action_id,
            "run": workflow_id,
        }
        await self._send(
            self._workflow.decide_action(workflow_id, action_id, approve=approve, by=user.username),
            event,
        )
        return Decided(workflow_id, decision, await self._reread(workflow_id))

    # ── Internals ───────────────────────────────────────────────────────────

    async def _require(self, ref: ClusterRef) -> None:
        """The day1 repo has the cluster's file (``ResourceNotFoundError`` otherwise)."""
        await self._clusters.hosted_cluster(ref)

    async def _send(self, call: Awaitable[None], event: Mapping[str, str]) -> None:
        try:
            await call
        except AmbiguousDecisionError:
            _log(
                logging.WARNING,
                "upgrade decision unconfirmed",
                "upgrade_decision_unconfirmed",
                event,
            )
            raise
        _log(logging.INFO, "upgrade decided", "upgrade_decided", event)

    async def _reread(self, workflow_id: str) -> UpgradeRun | None:
        """The run after a decision; a failed read does not undo the decision."""
        try:
            return await self._workflow.run(workflow_id)
        except WorkflowsError as exc:
            logger.info("upgrade run %s not read after a decision: %s", workflow_id, exc)
            return None


def _check(decision: UpgradeDecision, *, reason: str | None, nodepool: str | None) -> None:
    """What the workflow's bodies require: a reason where needed, a NodePool only to continue."""
    problems: list[str] = []
    if decision.needs_reason and not (reason and reason.strip()):
        problems.append(f"{decision.value} needs a reason")
    if reason and not decision.takes_reason:
        problems.append(f"{decision.value} takes no reason")
    if nodepool and decision is not UpgradeDecision.CONTINUE:
        problems.append("only continue names a NodePool")
    if problems:
        raise InvalidInputError(f"{decision.value} cannot be sent like this", problems)


def _where(ref: ClusterRef, user: User) -> dict[str, str]:
    return {"user": user.username, "cluster": ref.name, "site": ref.site, "mce": ref.mce}


def _log(level: int, message: str, name: str, event: Mapping[str, str]) -> None:
    fields = " ".join(f"{key}={value}" for key, value in event.items())
    logger.log(level, "%s: %s", message, fields, extra={"event": name, **event})
