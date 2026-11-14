"""The Rules & Policies page: what server-scan runs (ADR-0048's 3.30.0 amendment).

server-scan's ``GET /api/v1/classification-rules`` and ``/health-policies``
(their ``ClassificationRuleResponse`` and ``HealthPolicyResponse`` in
``backend/app/api/v1/classification_schemas.py`` and ``health_policy_schemas.py``,
team-redbull/server-scan at 92146d3): the rules that give a server its
installation type from its own fields, and the policies that judge its
health. Both ship in server-scan's code and are seeded at its start-up;
nothing writes them through its API. Typed in its shape, with its domain
models' defaults, so the web's port of server-scan's TypeScript reads day1's
answer as it is. Read strictly (``SHAPE``): a value of the wrong type fails
the read, never becomes a blank. server-scan's words (an installation type,
a severity, a source, a collector, an operator) stay strings, so a word it
adds later still reaches the page; a condition's ``value`` and ``equals`` are
whatever JSON the policy holds.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, JsonValue

from wingman_day1.domain.server_scan_hardware import SHAPE

# ── Classification rules ───────────────────────────────────────────────────────


class RuleScope(BaseModel):
    """The vendor, collector (``manager_type``) and site a rule is kept to; none: every server."""

    model_config = SHAPE

    vendor: str | None = None
    manager_type: str | None = None
    site_id: str | None = None


class RuleFlags(BaseModel):
    """How the rule's pattern is compiled."""

    model_config = SHAPE

    ignore_case: bool = True
    multiline: bool = False
    dotall: bool = False


class RuleStats(BaseModel):
    """What server-scan counted while running the rule."""

    model_config = SHAPE

    last_matched_at: datetime | None = None
    timeout_count: int = 0
    quarantined: bool = False


class ClassificationRule(BaseModel):
    """One rule: ``field ~ pattern`` gives ``installation_type``; higher ``priority`` first."""

    model_config = SHAPE

    id: str
    name: str
    description: str = ""
    enabled: bool = True
    system: bool = False
    installation_type: str
    scope: RuleScope = RuleScope()
    field: str
    pattern: str
    flags: RuleFlags = RuleFlags()
    source: str
    priority: int
    order: int = 0
    stats: RuleStats = RuleStats()
    revision: int = 1
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None


class ClassificationRuleList(BaseModel):
    """The enabled classification rules, in server-scan's order."""

    model_config = SHAPE

    items: tuple[ClassificationRule, ...]


# ── Health policies ───────────────────────────────────────────────────────────


class Condition(BaseModel):
    """A node of a policy's condition: ``all_of``, ``any_of``, ``not`` or a metric leaf.

    server-scan sends every field on every node, the unused ones ``null``.
    """

    model_config = SHAPE

    all_of: tuple[Condition, ...] | None = None
    any_of: tuple[Condition, ...] | None = None
    not_: Condition | None = Field(default=None, alias="not")
    metric: str | None = None
    operator: str | None = None
    value: JsonValue = None
    equals: JsonValue = None


class EvidenceField(BaseModel):
    """A metric a fired policy cites, under the key its message uses."""

    model_config = SHAPE

    key: str
    metric: str


class PolicyScope(BaseModel):
    """The site, vendor and collectors a policy is kept to; none: every server."""

    model_config = SHAPE

    site_id: str | None = None
    vendor: str | None = None
    manager_types: tuple[str, ...] = ()


class PolicyStats(BaseModel):
    """What server-scan counted while running the policy."""

    model_config = SHAPE

    fire_count: int = 0
    last_fired_at: datetime | None = None
    error_count: int = 0
    quarantined: bool = False


class HealthPolicy(BaseModel):
    """One policy: when ``condition`` holds, ``category`` is at least ``severity``.

    Policies sharing a ``policy_key`` are one family: the most specific,
    highest-priority enabled one is evaluated and the rest are shadowed.
    """

    model_config = SHAPE

    id: str
    name: str
    description: str = ""
    enabled: bool = True
    system: bool = False
    policy_key: str
    mode: str = "EVALUATE"
    category: str
    severity: str
    condition: Condition
    evidence: tuple[EvidenceField, ...] = ()
    message_template: str
    scope: PolicyScope = PolicyScope()
    source: str
    priority: int
    order: int = 0
    stats: PolicyStats = PolicyStats()
    revision: int = 1
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None


class HealthPolicyList(BaseModel):
    """The enabled health policies, in server-scan's order."""

    model_config = SHAPE

    items: tuple[HealthPolicy, ...]
