"""The bodies of ``/api/day1/seeds/{seed}``: a new KV cluster's draft and its create (ADR-0069)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from wingman_day1.api.v1.schemas import _In
from wingman_day1.application.kv_clusters import KvChoices, KvDraft
from wingman_day1.domain.kv_clusters import MAX_KV_WORKERS
from wingman_day1.domain.kv_create import DEFAULT_KV_WORKERS, STANDBY_WORKERS, KvModel

Workers = Annotated[int, Field(ge=1, le=MAX_KV_WORKERS)]
Owner = Annotated[str, Field(min_length=1, max_length=10, pattern=r"^[0-9]+$")]


class KvModelOut(BaseModel):
    """The KV cluster a new one copies its owner, configs and tuning profiles from."""

    name: str
    site: str
    seed: str
    configs: list[str]
    tuning_config: str | list[str] | None
    """Its first NodePool's ``tuningConfig``: one profile, several, or none."""

    @classmethod
    def of(cls, model: KvModel) -> KvModelOut:
        """From a model."""
        tuning = model.tuning_config
        if isinstance(tuning, list):
            tuning = [str(name) for name in tuning]
        return cls(
            name=model.ref.name,
            site=model.ref.site,
            seed=model.ref.mce,
            configs=list(model.configs),
            tuning_config=tuning if isinstance(tuning, str | list) else None,
        )


class KvDraftOut(BaseModel):
    """``GET /seeds/{seed}/kv-cluster-draft``: the new KV cluster's file as Wingman fills it."""

    seed: str
    site: str
    name: str | None
    """``ocp4-<lc>-kv-<site>-<zone>-<id>``, the lowest free id; ``None`` with ``problems``."""
    zone: str | None
    zones: list[str]
    """The seed name's zone, or the zones of its bare-metal InfraEnvs when it gives none."""
    mastertag: str | None
    versions: list[str]
    """The releases the seed offers, newest first, its default spelled as its values.yaml."""
    infra_env: str | None
    infra_envs: list[str]
    """The zone's bare-metal InfraEnvs (``<flavor>-mtl-<zone>``) to choose from."""
    infra_envs_from: Literal["hub", "files"]
    """``hub``: read live; ``files``: what the seed's KV clusters name (live status off)."""
    workers: int
    default_workers: int
    max_workers: int
    standby_workers: list[int]
    """The capacity policy's ``standbyWorkers`` range, ``[1, 5]``: a standby KV cluster's size."""
    model: KvModelOut | None
    """``None`` when no KV cluster exists: the owner is then the request's, no configs."""
    owner: dict[str, str]
    path: str | None
    yaml: str | None
    """The file provision-cluster gets; ``None`` while ``problems`` say why not."""
    problems: list[str]

    @classmethod
    def of(cls, draft: KvDraft) -> KvDraftOut:
        """From a draft."""
        ref = draft.ref
        return cls(
            seed=draft.seed,
            site=draft.site,
            name=draft.name,
            zone=draft.zone,
            zones=list(draft.zones),
            mastertag=draft.mastertag,
            versions=list(draft.versions),
            infra_env=draft.infra_env,
            infra_envs=list(draft.infra_envs),
            infra_envs_from="hub" if draft.infra_envs_from == "hub" else "files",
            workers=draft.workers,
            default_workers=DEFAULT_KV_WORKERS,
            max_workers=MAX_KV_WORKERS,
            standby_workers=list(STANDBY_WORKERS),
            model=KvModelOut.of(draft.model) if draft.model else None,
            owner=dict(draft.owner),
            path=str(ref.path) if ref else None,
            yaml=draft.content,
            problems=list(draft.problems),
        )


class KvOwnerIn(_In):
    """The owner numbers, when no KV cluster exists to copy them from (ADR-0028)."""

    merkaz: Owner
    anaf: Owner
    mador: Owner


class CreateKvClusterIn(_In):
    """``POST /seeds/{seed}/kv-clusters``: the draft's choices, and the name it showed."""

    name: str = Field(min_length=1, max_length=63)
    """The name the draft showed; another free name now is a 409, never a silent other one."""
    zone: str | None = Field(default=None, min_length=1, max_length=63)
    infra_env: str | None = Field(default=None, min_length=1, max_length=253)
    mastertag: str | None = Field(default=None, min_length=1, max_length=64)
    workers: Workers = DEFAULT_KV_WORKERS
    owner: KvOwnerIn | None = None
    """Read only when no KV cluster exists to copy the owner from."""

    def choices(self) -> KvChoices:
        """As the use case takes them."""
        owner = self.owner.model_dump() if self.owner else {}
        return KvChoices(self.zone, self.infra_env, self.mastertag, self.workers, owner)
