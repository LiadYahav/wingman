"""Runs of the platform's workflows that act on one cluster.

The workflows own every operation with more than one step or system;
Wingman starts the ones a customer asks for and shows how they are going
(``docs/ideas/architecture-fit.md``). Only data crosses back: a run's id,
its status, the step it is on and its error.
"""

from __future__ import annotations

from dataclasses import dataclass


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
