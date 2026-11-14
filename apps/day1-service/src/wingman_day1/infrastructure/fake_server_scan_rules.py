"""The fake fleet's rules and policies: Rules & Policies with ``DAY1_FAKE_FLEET=true`` (ADR-0048).

``dev/fleet-fixtures/rules.yaml`` holds, in the shapes of server-scan's
``GET /api/v1/classification-rules`` and ``/health-policies`` answers, the
classification rules the fake servers' records name and server-scan's own
seeded health policies, read by the same strict models as the real answers
(through JSON, as the HTTP adapter reads them), so the fixture cannot drift
from the shapes. Nothing here is real.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import yaml

from wingman_day1.domain.server_scan_rules import ClassificationRuleList, HealthPolicyList

RULES_FILE: Final = Path("dev/fleet-fixtures/rules.yaml")


@dataclass(frozen=True, slots=True)
class FakeRules:
    """What the fake server-scan runs: its classification rules and health policies."""

    rules: ClassificationRuleList = field(default_factory=lambda: ClassificationRuleList(items=()))
    policies: HealthPolicyList = field(default_factory=lambda: HealthPolicyList(items=()))


def default_rules_file() -> Path:
    """``dev/fleet-fixtures/rules.yaml`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / RULES_FILE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{RULES_FILE} not found above this file")


def load_rules(path: Path) -> FakeRules:
    """A fixture's rules and policies, in server-scan's answer shapes; a malformed one raises."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"{path}: expected a mapping")
    return FakeRules(
        rules=ClassificationRuleList.model_validate_json(json.dumps(raw["classification_rules"])),
        policies=HealthPolicyList.model_validate_json(json.dumps(raw["health_policies"])),
    )
