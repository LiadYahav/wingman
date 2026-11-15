"""The structured log line of an MCE placement decision (ADR-0050).

Every create that passes the placement rule logs ``mce_placement_chosen``
with the pick, an override and its reason, and each candidate's numbers, so
an operator can see why a cluster went where it went.
"""

from __future__ import annotations

import logging

from wingman_core.domain.users import User
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.placement import Admission

logger = logging.getLogger(__name__)


def log_placement(admission: Admission, ref: ClusterRef, user: User) -> None:
    """The decision and its numbers, as the structured event ``mce_placement_chosen``."""
    placement = admission.placement
    event = {
        "cluster": ref.name,
        "site": ref.site,
        "mce": admission.chosen,
        "pick": placement.pick,
        "override": admission.override,
        "reason": admission.reason,
        "requested_by": user.username,
        "candidates": [
            {
                "mce": c.mce,
                "rank": c.rank,
                "clusters": c.picture.clusters,
                "owner_clusters": c.picture.owner_clusters,
                "spare_usable": c.picture.spare.usable if c.picture.spare else None,
                "free_pods": c.picture.pods.free if c.picture.pods else None,
                "failures": list(c.failures),
            }
            for c in placement.candidates
        ],
    }
    logger.info(
        "MCE placement for %s: %s%s",
        ref.name,
        admission.chosen,
        f" over the pick {placement.pick}" if admission.override else " (the pick)",
        extra={"event": "mce_placement_chosen", **event},
    )
