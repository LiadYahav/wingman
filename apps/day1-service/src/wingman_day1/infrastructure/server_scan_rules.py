"""server-scan's rules and policies for the Rules & Policies page (ADR-0048's 3.30.0 amendment).

``GET /api/v1/classification-rules?enabled=true`` and
``GET /api/v1/health-policies?enabled=true`` with the viewer token
(server-scan serves both to any authenticated caller): the enabled ones only,
as server-scan's page asks, since a disabled rule is not something the
deployment does. Read strictly into the domain's models of server-scan's
shapes (``domain/server_scan_rules.py``): an answer that does not fit is
"unavailable", never a blank.
"""

from __future__ import annotations

from typing import Final

import httpx

from wingman_day1.domain.server_scan_rules import ClassificationRuleList, HealthPolicyList
from wingman_day1.infrastructure.server_scan_record import check, fetch, parsed

RULES_PATH: Final = "/api/v1/classification-rules"
POLICIES_PATH: Final = "/api/v1/health-policies"
ENABLED_ONLY: Final = {"enabled": "true"}


async def read_rules(client: httpx.AsyncClient) -> ClassificationRuleList:
    """The enabled classification rules, in the order server-scan tries them."""
    what = "listing classification rules"
    response = await fetch(client, RULES_PATH, what=what, params=ENABLED_ONLY)
    check(response, what=what)
    return parsed(ClassificationRuleList, response, "malformed classification rules")


async def read_policies(client: httpx.AsyncClient) -> HealthPolicyList:
    """The enabled health policies."""
    what = "listing health policies"
    response = await fetch(client, POLICIES_PATH, what=what, params=ENABLED_ONLY)
    check(response, what=what)
    return parsed(HealthPolicyList, response, "malformed health policies")
