"""``/api/day1/seeds/{seed}``: a new KV cluster on a seed, through provision-cluster (ADR-0069).

Admins only (``AdminUser``): a viewer never knows of a seed or a KV cluster
(ADR-0067, ADR-0068), so a viewer's ``403`` comes before anything is read,
the same for every name. The draft is read as often as the dialog's choices
change; the create starts the workflow with exactly the draft's file, and its
run is read by ``GET /api/day1/clusters/{name}/provision-run``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from wingman_core.web.auth import AdminUser
from wingman_day1.api.deps import KvClusters
from wingman_day1.api.v1.cluster_workflows_schemas import ProvisionRunOut
from wingman_day1.api.v1.kv_clusters_schemas import CreateKvClusterIn, KvDraftOut, Workers
from wingman_day1.application.kv_clusters import KvChoices
from wingman_day1.domain.kv_create import DEFAULT_KV_WORKERS

router = APIRouter(prefix="/api/day1/seeds", tags=["seeds"])

Seed = Annotated[str, Path(min_length=1, max_length=63)]
Choice = Annotated[str | None, Query(min_length=1, max_length=253)]
OwnerNumber = Annotated[str | None, Query(min_length=1, max_length=10, pattern=r"^[0-9]+$")]


@router.get("/{seed}/kv-cluster-draft")
async def kv_cluster_draft(  # the dialog's choices, each optional
    seed: Seed,
    user: AdminUser,
    kv: KvClusters,
    zone: Choice = None,
    infra_env: Choice = None,
    mastertag: Choice = None,
    workers: Annotated[Workers, Query()] = DEFAULT_KV_WORKERS,
    owner_merkaz: OwnerNumber = None,
    owner_anaf: OwnerNumber = None,
    owner_mador: OwnerNumber = None,
) -> KvDraftOut:
    """The next KV cluster on the seed: its name, zone, version, pool, model and file.

    ``problems`` say why it cannot be created as chosen, with the choices
    still listed; a folder that is not a seed is ``404``. The owner numbers
    are read only when no KV cluster exists to copy them from.
    """
    owners = {"merkaz": owner_merkaz, "anaf": owner_anaf, "mador": owner_mador}
    owner = {key: value for key, value in owners.items() if value}
    choices = KvChoices(zone, infra_env, mastertag, workers, owner)
    return KvDraftOut.of(await kv.draft(seed, choices))


@router.post("/{seed}/kv-clusters", status_code=202)
async def create_kv_cluster(
    seed: Seed, body: CreateKvClusterIn, user: AdminUser, kv: KvClusters
) -> ProvisionRunOut:
    """Start provision-cluster on the seed with the draft's file (ADR-0042): 202 with the run.

    ``422`` with the draft's problems, ``409`` when the next free name is no
    longer ``name``; the orchestrator's own refusals are shown in its words.
    Never retried (ADR-0006).
    """
    return ProvisionRunOut.of(await kv.create(seed, body.name, body.choices(), user=user))
