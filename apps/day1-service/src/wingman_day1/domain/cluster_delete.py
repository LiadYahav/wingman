"""Deleting a cluster's file: what its merge request says, and what a KV cluster's asks (ADR-0067).

A KV cluster is a hosted cluster like any other, and an admin edits, scales,
uninstalls a node of and upgrades it as a tenant's. Only its delete differs:
its workers host tenants' VM workers, so deleting it deletes those VMs. The
admin types the cluster's name to confirm (``confirm``), day1 refuses the
delete without it, and the merge request says what goes with it.
"""

from __future__ import annotations

from typing import Final

from wingman_core.domain.cluster_kinds import HostedClusterKind
from wingman_day1.domain.paths import ClusterRef

KV_VMS: Final = "the tenants' VM workers it hosts are deleted with it"


def delete_summary(ref: ClusterRef) -> str:
    """The delete merge request's words: what merging removes, and for a KV cluster its VMs."""
    summary = (
        f"Deleting hosted cluster **{ref.name}** (site `{ref.site}`, MCE `{ref.mce}`). Merging "
        "removes its Argo Application. Its VLAN segment is released only where the chart's "
        "PostDelete hook exists."
    )
    if ref.kind is HostedClusterKind.KV:
        summary += f" It is a KV cluster on seed `{ref.mce}`: {KV_VMS}."
    return summary


def delete_confirm_problems(ref: ClusterRef, confirm: str | None) -> list[str]:
    """Why a delete may not go ahead: a KV cluster's needs its name typed in, ``confirm``."""
    if ref.kind is HostedClusterKind.TENANT or confirm == ref.name:
        return []
    return [
        f"{ref.name} is a KV cluster: {KV_VMS}. Type its name to confirm "
        f"(confirm={ref.name}); got {confirm!r}"
    ]
