"""The Confs page: server-scan's hardware catalog (ADR-0048's 3.29.0 amendment).

server-scan's ``GET /api/v1/confs`` (its ``ConfListResponse`` and ``Conf`` in
``backend/app/api/v1/confs_schemas.py`` and ``backend/app/domain/models/conf.py``,
team-redbull/server-scan at 92146d3): every server configuration (spec) in
its ``confs`` collection, which another system writes, in natural
``conf_id`` order, unpaged, and the id of each stored document it could not
read. The shape is that writer's, reproduced field for field by server-scan,
and here, with its defaults: the web's port of server-scan's TypeScript reads
day1's answer as it is. Read strictly (``SHAPE``): a value of the wrong type
fails the read, never becomes a blank. Words the writer picks (a disk type,
``"unknown"``) stay strings.
"""

from __future__ import annotations

from pydantic import BaseModel

from wingman_day1.domain.server_scan_hardware import SHAPE


class ConfCpuCache(BaseModel):
    """Per-level cache sizes of one CPU, in KB."""

    model_config = SHAPE

    l1: int
    l2: int
    l3: int


class ConfCpu(BaseModel):
    """The processors a conf carries."""

    model_config = SHAPE

    model: str
    vendor: str | None = None
    sockets: int
    cores_per_cpu: int
    total_cores_ht: int
    clock_mhz: int
    max_clock_mhz: int
    cache_kb: ConfCpuCache


class ConfRam(BaseModel):
    """The memory: ``total_gib`` 0 is a failed scan, ``type`` empty a failed DIMM read."""

    model_config = SHAPE

    total_gib: int
    dimms: int
    per_dimm_gb: int
    type: tuple[str, ...] = ()


class ConfDisk(BaseModel):
    """One group of drives of one type and size; the writer records no drive model."""

    model_config = SHAPE

    count: int
    type: str
    capacity_tb: float


class ConfGpu(BaseModel):
    """One group of identical GPUs."""

    model_config = SHAPE

    count: int
    model: str


class ConfAdapter(BaseModel):
    """One group of network adapters with the same port count and speed (Gb/s per port)."""

    model_config = SHAPE

    count: int
    ports: int
    speed: float


class Conf(BaseModel):
    """One server configuration (spec); no ``part_number`` is a conf with no catalog match."""

    model_config = SHAPE

    conf_id: str
    part_number: str | None = None
    model: str
    cpu: ConfCpu
    ram: ConfRam
    disks: tuple[ConfDisk, ...] = ()
    gpus: tuple[ConfGpu, ...] = ()
    gpu_count: int = 0
    gpu_vram_gb: float | None = None
    adapters: tuple[ConfAdapter, ...] = ()
    adapter_count: int = 0


class ConfList(BaseModel):
    """Every readable conf in server-scan's order, and the ``conf_id`` of each it skipped."""

    model_config = SHAPE

    items: tuple[Conf, ...]
    unreadable: tuple[str, ...] = ()
