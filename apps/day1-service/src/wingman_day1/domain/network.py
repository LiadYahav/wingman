"""A cluster's network: read from its file, checked against segments-manager (ADR-0039).

Git is the source of truth. The allocate-segment workflow writes ``vlanId``
and ``dhcp_values.network`` into the cluster file on the MR branch, and the
cluster's segment is that network as a /24: segments-manager's segments are
always /24 (``docs/ecosystem/notes/segments-manager.md``).

segments-manager only adds what the file does not carry, the ACI EPG, and is
checked against the file: what it says that disagrees with Git becomes a
plain-words problem. The values shown are always the file's. Nothing is ever
written to segments-manager.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

SEGMENT_PREFIX: Final = 24
"""Every segment in segments-manager is a /24."""
ALLOCATED: Final = "Allocated"
"""The status of a segment held by a cluster (the other is ``Available``)."""


def segment_of(network: str | None) -> str | None:
    """``a.b.c.0/24`` for the file's ``dhcp_values.network``; ``None`` when it is not one.

    ``None`` when the file has no network yet, and when the value is not a
    /24's network address (``10.20.90.5``, ``10.20.90``): Wingman does not guess.
    """
    if not network:
        return None
    try:
        return str(ipaddress.IPv4Network(f"{network.strip()}/{SEGMENT_PREFIX}", strict=True))
    except ValueError:
        return None


def vlan_of(raw: object) -> int | None:
    """The file's ``vlanId`` as a number: an int, or a string of digits; else ``None``."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


@dataclass(frozen=True, slots=True)
class FileNetwork:
    """The cluster's network as its file has it; ``None`` until allocate-segment has written it."""

    vlan_id: int | None
    segment: str | None


def file_network(vlan_id: object, dhcp_network: str | None) -> FileNetwork:
    """The network from a file's raw ``vlanId`` and its ``dhcp_values.network``."""
    return FileNetwork(vlan_id=vlan_of(vlan_id), segment=segment_of(dhcp_network))


@dataclass(frozen=True, slots=True)
class SegmentRecord:
    """One segment as segments-manager records it (``GET /api/segments/by-segment``)."""

    segment: str
    vlan_id: int | None
    epg_name: str | None
    cluster_name: str | tuple[str, ...] | None
    """A cluster file's stem; a list for a shared ``UPI`` segment; ``None`` while Available."""
    status: str | None
    type: str | None
    site: str | None
    dhcp: bool | None = None
    allocated_at: str | None = None
    """Set on allocation and never cleared: an Available segment may still carry one."""


@dataclass(frozen=True, slots=True)
class NetworkView:
    """What the cluster page shows: the file's network, the EPG, and what disagrees."""

    vlan_id: int | None
    segment: str | None
    epg: str | None = None
    ledger: SegmentRecord | None = None
    """segments-manager's record; ``None`` when it was not asked, failed, or has none."""
    problems: tuple[str, ...] = field(default=())
    ledger_error: str | None = None
    """Why segments-manager could not be read; the file's values are shown regardless."""


def unchecked(file: FileNetwork, *, ledger_error: str | None = None) -> NetworkView:
    """The file's network alone: segments-manager is off, failed, or there is no segment yet."""
    return NetworkView(vlan_id=file.vlan_id, segment=file.segment, ledger_error=ledger_error)


def checked(file: FileNetwork, record: SegmentRecord | None, *, cluster: str) -> NetworkView:
    """The file's network with segments-manager's answer for its segment.

    ``cluster`` is the file's stem: the ``cluster_name`` allocate-segment gives
    segments-manager (ADR-0014). ``record`` is ``None`` when segments-manager
    has no such segment.
    """
    return NetworkView(
        vlan_id=file.vlan_id,
        segment=file.segment,
        epg=record.epg_name if record else None,
        ledger=record,
        problems=disagreements(file, record, cluster=cluster),
    )


def disagreements(
    file: FileNetwork, record: SegmentRecord | None, *, cluster: str
) -> tuple[str, ...]:
    """What segments-manager says that disagrees with the file, one sentence each."""
    if file.segment is None:
        return ()
    if record is None:
        return (f"segments-manager has no segment {file.segment}",)
    problems: list[str] = []
    if record.status != ALLOCATED:
        status = (
            f"marks this segment {record.status}"
            if record.status
            else "gives this segment no status"
        )
        problems.append(f"segments-manager {status}, not {ALLOCATED}")
    elif (holder := _holder_problem(record.cluster_name, cluster)) is not None:
        problems.append(holder)
    if record.vlan_id != file.vlan_id:
        theirs = f"VLAN {record.vlan_id}" if record.vlan_id is not None else "no VLAN"
        ours = f"has {file.vlan_id}" if file.vlan_id is not None else "has no vlanId"
        problems.append(f"segments-manager has {theirs} for this segment; the file {ours}")
    return tuple(problems)


def _holder_problem(holder: str | Sequence[str] | None, cluster: str) -> str | None:
    """Why ``holder`` is not ``cluster``, or ``None`` when it is (or a shared list has it)."""
    if holder is None:
        return "segments-manager allocated this segment to no cluster"
    if isinstance(holder, str):
        if holder == cluster:
            return None
        return f"segments-manager allocated this segment to {holder}, not to {cluster}"
    if cluster in holder:
        return None
    shared = ", ".join(holder) or "no cluster"
    return f"segments-manager shares this segment among {shared}, not with {cluster}"
