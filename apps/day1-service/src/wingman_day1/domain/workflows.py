"""Runs of the platform's workflows that act on one cluster.

The workflows own every operation with more than one step or system;
Wingman starts the ones a customer asks for and shows how they are going
(``docs/ideas/architecture-fit.md``). Only data crosses back: a run's id,
its status, the step it is on and its error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

PROVISION_WORKFLOW_PREFIX: Final = "provision-cluster-"
"""A cluster's provision run is ``provision-cluster-<file stem>`` (ADR-0042)."""


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
