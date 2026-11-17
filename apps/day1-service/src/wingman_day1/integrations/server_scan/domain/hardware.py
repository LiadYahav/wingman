"""A server's hardware, as server-scan's server page shows it (ADR-0048's 3.25.0 amendment).

The shapes are server-scan's (``backend/app/domain/models/hardware.py`` and
its UI's ``frontend/src/types/server.ts`` in team-redbull/server-scan at
92146d3), holding the fields its UI reads, so day1 answers in server-scan's
own shape and server-scan's TypeScript applies as it is (decision 18 of
``docs/ideas/single-pane.md``). Read strictly (``SHAPE``): a value of the
wrong type fails the read, never becomes a blank. Words server-scan picks
(a health, a media type, a controller's kind) stay strings, so a word it adds
later still reaches the page. ``server_scan_record`` holds the rest.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict

SHAPE: Final = ConfigDict(frozen=True, extra="ignore", strict=True)
"""Immutable, strict, and blind to server-scan's fields the page never reads."""


class Cpu(BaseModel):
    """Sockets, cores, threads and the model; a count never read is 0."""

    model_config = SHAPE

    sockets: int
    cores: int
    threads: int
    model: str | None


class MemoryModule(BaseModel):
    """One DIMM. ``health`` is a severity or the collector's own word (Cisco: UP/DOWN)."""

    model_config = SHAPE

    slot: str | None
    size_bytes: int | None
    speed_mhz: int | None
    health: str | None
    health_detail: str | None
    """The vendor's raw word ``health`` was reduced from; diagnosis only."""


class Memory(BaseModel):
    """The total, in bytes, and every module."""

    model_config = SHAPE

    total_bytes: int
    modules: tuple[MemoryModule, ...]


class StorageDrive(BaseModel):
    """One physical drive."""

    model_config = SHAPE

    id: str
    model: str | None
    serial: str | None
    media_type: str
    capacity_bytes: int | None
    health: str | None
    health_detail: str | None


class StorageVolume(BaseModel):
    """One virtual drive on a controller."""

    model_config = SHAPE

    id: str
    raid_type: str | None
    volume_type: str | None
    capacity_bytes: int | None
    health: str | None


class StorageController(BaseModel):
    """A storage controller and its volumes; ``kind`` is RAID, BOSS, AHCI, NVME or OTHER."""

    model_config = SHAPE

    id: str
    name: str | None
    kind: str
    volumes: tuple[StorageVolume, ...]


class RaidDetection(BaseModel):
    """Whether the OS is on RAID 1 (``PRESENT``, ``ABSENT``, ``UNKNOWN``), and how it was told."""

    model_config = SHAPE

    state: str
    method: str | None
    bmc: str | None
    reason: str | None


class Storage(BaseModel):
    """The total, every drive, the controllers and the RAID check.

    ``controllers`` and ``raid`` are absent from a document server-scan wrote
    before it read them: empty and ``None`` then.
    """

    model_config = SHAPE

    total_bytes: int
    drives: tuple[StorageDrive, ...]
    controllers: tuple[StorageController, ...] = ()
    raid: RaidDetection | None = None


class Gpu(BaseModel):
    """One GPU, with what server-scan's GPU table shows."""

    model_config = SHAPE

    vendor: str | None
    model: str | None
    serial: str | None
    memory_bytes: int | None
    health: str | None
    health_detail: str | None
    pci_address: str | None
    firmware_version: str | None
    memory_type: str | None
    ecc_mode_enabled: bool | None
    correctable_error_count: int | None
    uncorrectable_error_count: int | None
    temperature_celsius: float | None
    power_watts: float | None


class Psu(BaseModel):
    """One power supply: its rating and what it draws now."""

    model_config = SHAPE

    id: str
    model: str | None
    serial: str | None
    health: str | None
    health_detail: str | None
    capacity_watts: int | None
    power_watts: float | None


class Power(BaseModel):
    """Every power supply."""

    model_config = SHAPE

    psus: tuple[Psu, ...]


class Hardware(BaseModel):
    """The Hardware tab: CPU, memory, storage, GPUs and power."""

    model_config = SHAPE

    cpu: Cpu
    memory: Memory
    storage: Storage
    gpus: tuple[Gpu, ...]
    power: Power
