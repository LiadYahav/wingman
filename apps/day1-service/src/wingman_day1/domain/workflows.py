"""Runs of the platform's workflows that act on one cluster.

The workflows own every operation with more than one step or system;
Wingman starts the ones a customer asks for and shows how they are going
(``docs/ideas/architecture-fit.md``). Only data crosses back: a run's id,
its status, the step it is on and its error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

WorkflowName = Literal["provision-cluster"]
"""The platform workflows whose day1 merge requests Wingman shows (ADR-0042's amendment)."""
PROVISION_WORKFLOW: Final[WorkflowName] = "provision-cluster"
"""The platform's workflow that creates a cluster (ADR-0042)."""
PROVISION_WORKFLOW_PREFIX: Final = "provision-cluster-"
"""A cluster's provision run is ``provision-cluster-<file stem>`` (ADR-0042)."""
PROVISION_BRANCH_PREFIX: Final = "provision-cluster/"
"""The workflow's day1 merge request is on ``provision-cluster/<file stem>`` (ADR-0042)."""


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    """One run, as the orchestrator reports it."""

    workflow_id: str
    status: str
    """The orchestrator's status, lowercase: ``running``, ``completed``, ``failed``, ..."""
    phase: str | None = None
    """The step it is on (for delete: ``draining``, ``awaiting-prune``, ...)."""
    error: str | None = None
    """Why it failed, in the orchestrator's words."""


def provision_workflow_id(stem: str) -> str:
    """The id of the provision run for the cluster file ``<stem>.yaml``."""
    return f"{PROVISION_WORKFLOW_PREFIX}{stem}"


def provision_branch_stem(branch: str) -> str | None:
    """The cluster file stem the provision-cluster workflow's ``branch`` creates, else ``None``.

    The workflow proposes ``ocp4-<name>.yaml`` on ``provision-cluster/ocp4-<name>``
    (its ``provision_cluster_branch``), with no label and its own title, and a
    re-run reuses the branch and its merge request. The branch is the only
    sign the merge request is the workflow's (ADR-0042's amendment).
    """
    stem = branch.removeprefix(PROVISION_BRANCH_PREFIX)
    if stem == branch or not stem or "/" in stem:
        return None
    return stem


@dataclass(frozen=True, slots=True)
class ProvisionRun:
    """A provision-cluster run, as the orchestrator reports it (ADR-0042).

    Wingman keeps no list of its phases: ``phase`` is the workflow's own word.
    """

    workflow_id: str
    status: str
    """The orchestrator's status, lowercase: ``running``, ``completed``, ``failed``, ..."""
    phase: str | None = None
    error: str | None = None
    """Why it failed, in the workflow's words."""
    merge_request_url: str | None = None
    """The merge request the workflow opened, once it has."""
    merge_request_state: str | None = None

    @property
    def cluster(self) -> str:
        """The cluster file's stem the run provisions."""
        return self.workflow_id.removeprefix(PROVISION_WORKFLOW_PREFIX)
