"""The bodies of the platform workflows the clusters router starts or shows.

``GET /provisioner`` says whether Create opens Wingman's MR or starts
``provision-cluster`` (ADR-0042), and ``/{name}/provision-run`` shows that run;
``/{name}/delete-workflow`` shows and starts the delete-cluster workflow
(ADR-0033). A run's own body, ``WorkflowRunOut``, is in ``schemas.py``: node
uninstall answers with it too.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from wingman_day1.api.v1.schemas import WorkflowRunOut
from wingman_day1.domain.workflows import ProvisionRun


class ProvisionRunOut(BaseModel):
    """A provision-cluster run (ADR-0042): the workflow's own status, phase and merge request."""

    workflow_id: str
    cluster: str
    """The cluster file's stem the run provisions."""
    status: str
    phase: str | None
    """The workflow's own word (``awaiting-merge``); Wingman keeps no list of them."""
    error: str | None
    merge_request_url: str | None
    """The merge request the workflow opened, once it has."""
    merge_request_state: str | None

    @classmethod
    def of(cls, run: ProvisionRun) -> ProvisionRunOut:
        """From a run."""
        return cls(
            workflow_id=run.workflow_id,
            cluster=run.cluster,
            status=run.status,
            phase=run.phase,
            error=run.error,
            merge_request_url=run.merge_request_url,
            merge_request_state=run.merge_request_state,
        )


class ProvisionerOut(BaseModel):
    """``GET /clusters/provisioner``: what Create does in this deployment (ADR-0042)."""

    mode: Literal["merge-request", "workflow"]


class DeleteWorkflowOut(BaseModel):
    """``GET /clusters/{name}/delete-workflow``: the newest run, if any."""

    run: WorkflowRunOut | None


class StartDeleteWorkflowIn(BaseModel):
    """``POST /clusters/{name}/delete-workflow``: deleting is not reversible, so say so."""

    model_config = ConfigDict(extra="forbid")

    confirm: Literal[True]
