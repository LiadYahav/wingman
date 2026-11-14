"""A server's record, as server-scan's server page shows it (ADR-0048's 3.25.0 amendment).

server-scan's ``GET /api/v1/servers/{id}`` (its ``ServerDetail``) and
``/vm-host``, holding the fields its UI's ``frontend/src/types/server.ts``
reads (team-redbull/server-scan at 92146d3), typed and in its shape, so the
web's port of server-scan's TypeScript reads day1's answer as it is. Read
strictly; its internals the UI never reads are left out
(docs/notes/2026-11-13-server-scan-area-api.md §9.4). The hardware is in
``server_scan_hardware``.

Two differences from server-scan's answer: the maintenance keeps its dates
(Wingman's dialog sets an expected end), and the reservation says whether it
is ``held``, which server-scan computes for its rows only (``ReservationState``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from pydantic import BaseModel

from wingman_day1.domain.server_scan_hardware import SHAPE, Cpu, Hardware

HISTORY_OFF: Final = (
    "History needs server-scan's auditor token: add the key auditor-token to the server-scan "
    "Secret and restart day1 (SERVER_SCAN_AUDITOR_TOKEN)."
)


class ProfileTemplate(BaseModel):
    """The vendor's server profile template; both ``None`` for a standalone BMC."""

    model_config = SHAPE

    name: str | None
    external_id: str | None


class Identity(BaseModel):
    """What identifies the hardware."""

    model_config = SHAPE

    vendor: str
    serial: str | None
    system_uuid: str | None
    nic_macs: tuple[str, ...]


class BmcInfo(BaseModel):
    """The BMC's address as configured, split, and its MAC."""

    model_config = SHAPE

    address_raw: str | None
    scheme: str | None
    host: str | None
    port: int | None
    mac: str | None


class NetworkInterface(BaseModel):
    """One NIC port; ``location`` is ``controller/port/partition`` on Dell, else the BMC's id."""

    model_config = SHAPE

    name: str
    mac: str | None
    speed_mbps: int | None
    link_state: str
    location: str | None


class NetworkInfo(BaseModel):
    """The Network tab: the BMC and every interface, in server-scan's order."""

    model_config = SHAPE

    bmc: BmcInfo
    interfaces: tuple[NetworkInterface, ...]


class ConnectivityAttachment(BaseModel):
    """One link to a fabric interconnect; ``interface_kind`` is ``PHYSICAL`` or ``VNIC``."""

    model_config = SHAPE

    type: str
    provider: str | None
    fabric: str | None
    fabric_name: str | None
    fabric_id: str | None
    fabric_model: str | None
    fabric_serial: str | None
    server_interface: str | None
    server_port: str | None
    fabric_port: str | None
    admin_state: str
    oper_state: str
    speed_mbps: int | None
    last_seen: datetime | None
    interface_kind: str


class ConnectivityFacts(BaseModel):
    """The fabric paths in numbers."""

    model_config = SHAPE

    fabric_paths_total: int
    fabric_paths_up: int
    fabric_paths_down: int
    fabrics_present: tuple[str, ...]


class ConnectivityDetail(BaseModel):
    """The Connectivity tab: every attachment and the facts."""

    model_config = SHAPE

    attachments: tuple[ConnectivityAttachment, ...]
    facts: ConnectivityFacts


class Classification(BaseModel):
    """What the server was named to be, and the rule that said so."""

    model_config = SHAPE

    installation_type: str
    matched_rule_id: str | None
    matched_rule_name: str | None = None
    matched_field: str | None = None
    matched_pattern: str | None = None


class HealthReason(BaseModel):
    """One health policy that fired in the last evaluation."""

    model_config = SHAPE

    policy_key: str
    policy_name: str
    category: str
    severity: str
    message: str | None


class HealthSummary(BaseModel):
    """The overall health, each category's, and why (worst first)."""

    model_config = SHAPE

    overall: str
    memory: str
    storage: str
    network: str
    raid: str
    connectivity: str
    power: str
    gpu: str
    bmc: str
    name: str
    reasons: tuple[HealthReason, ...] = ()


class MaintenanceState(BaseModel):
    """Whether it is in maintenance, why, who (server-scan's actor id) and when."""

    model_config = SHAPE

    enabled: bool
    reason: str | None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    expected_end: datetime | None = None


class ReservationState(BaseModel):
    """The install lock (server-scan's ADR-0035) and whether it is ``held`` now."""

    model_config = SHAPE

    held: bool = False
    holder: str | None
    mce_cluster: str | None
    infra_env: str | None
    namespace: str | None = None
    workflow_id: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None

    def judged(self, now: datetime) -> ReservationState:
        """``held`` as server-scan judges its rows': a holder, and no expiry or one still ahead."""
        held = self.holder is not None and (self.expires_at is None or now < self.expires_at)
        return self.model_copy(update={"held": held})


class OpenShiftLifecycle(BaseModel):
    """What OpenShift reports: never reconciled with the classification (the two may disagree)."""

    model_config = SHAPE

    lifecycle_state: str
    cluster_name: str | None
    mce_name: str | None
    last_reported_at: datetime | None
    reported_by_agent_id: str | None
    reported_name: str | None
    contested_with: str | None
    contested_name: str | None


class VmHost(BaseModel):
    """Where a KubeVirt VM runs; ``node_name`` is ``None`` while it is stopped."""

    model_config = SHAPE

    cluster_name: str | None
    node_name: str | None


class ServerRecord(BaseModel):
    """One server, as server-scan's server page reads it (``GET /api/v1/servers/{id}``)."""

    model_config = SHAPE

    id: str
    name: str
    model: str | None
    profile_template: ProfileTemplate
    identity: Identity
    hardware: Hardware
    network: NetworkInfo
    connectivity: ConnectivityDetail
    classification: Classification
    health: HealthSummary
    maintenance: MaintenanceState
    reservation: ReservationState
    site_id: str | None
    manager_id: str | None
    source_provider: str | None
    openshift: OpenShiftLifecycle
    vm_host: VmHost | None = None
    """Set only for a KubeVirt VM."""
    unread_fields: tuple[str, ...]
    """Dotted paths the last collection could not read: the value there is carried forward."""
    nic_os_names: dict[str, str] = {}
    """A NIC's FQDD to its OS name, from server-scan's settings (never collected)."""
    tags: tuple[str, ...]
    last_seen_at: datetime | None
    stale: bool
    reachable: bool
    unreachable_since: datetime | None
    unreachable_reason: str | None
    updated_at: datetime
    created_at: datetime

    def judged(self, now: datetime) -> ServerRecord:
        """The record with its reservation's ``held`` judged at ``now``."""
        return self.model_copy(update={"reservation": self.reservation.judged(now)})


class VmHostServer(BaseModel):
    """The bare-metal server a VM runs on: what the VM's page shows beside it."""

    model_config = SHAPE

    id: str
    name: str
    vendor: str
    model: str | None
    site_id: str | None
    cpu: Cpu
    memory_total_bytes: int | None
    health: str
    maintenance: bool
    cluster_name: str | None


class VmHostAnswer(BaseModel):
    """``GET /api/v1/servers/{id}/vm-host``: a VM's host, resolved now.

    ``match`` is ``MEMBERSHIP``, ``NAME``, ``AMBIGUOUS``, ``NOT_IN_INVENTORY``
    or ``NOT_RUNNING``; ``host`` is set on the first two.
    """

    model_config = SHAPE

    cluster_name: str | None
    node_name: str | None
    match: str
    host: VmHostServer | None


def history_detail(*, viewer_token: bool, auditor_token: bool) -> str | None:
    """Why History does not work in this deployment; ``None`` when it does.

    As ``maintenance_detail``: with the auditor token it is read with it;
    with no token at all server-scan runs with auth off and needs none; a
    viewer token alone means auth is on, and server-scan keeps its audit
    trail from viewers.
    """
    if auditor_token or not viewer_token:
        return None
    return HISTORY_OFF
