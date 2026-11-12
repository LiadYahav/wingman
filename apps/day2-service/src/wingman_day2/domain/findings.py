"""Lint findings: one vocabulary for repo checks, API warnings and refused changes (ADR-0023).

A rule marked ``render_chain`` is one ``tools/render-verify/render_chain.py``
fails a snapshot on; Wingman reports it as an error with the same meaning,
and the oracle test holds the two to each other. The other rules are
Wingman's own: problems the platform renders without complaint but that
break or surprise at sync time.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    """How bad a finding is. An install that adds an ``error`` is refused."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Rule(StrEnum):
    """A named check. Values are stable: the web app and tests match on them."""

    ENV_NOT_ALLOWED = "env-not-allowed"
    DAY1_VERSION_MISSING = "day1-version-missing"
    MASTERTAG_MISSING = "mastertag-missing"
    MASTERTAG_INVALID = "mastertag-invalid"
    UPI_NAME_IN_CLUSTER = "upi-name-in-cluster"
    UPI_NAME_REUSED = "upi-name-reused"
    UPI_VERSION_FILE_INVALID = "upi-version-file-invalid"
    LEGACY_LAYOUT = "legacy-layout"
    EXCLUSIONS_HUB = "exclusions-hub"
    EXCLUSIONS_SCHEMA = "exclusions-schema"
    EXCLUSIONS_UNKNOWN_CHART = "exclusions-unknown-chart"
    EXCLUSIONS_UNKNOWN_TARGET = "exclusions-unknown-target"
    DUPLICATE_APP = "duplicate-app"
    REPOURL_MISCASED = "repourl-miscased"
    REPOURL_MISSING = "repourl-missing"
    REPOURL_MOVED = "repourl-moved"
    CHART_REPO_UNREADABLE = "chart-repo-unreadable"
    YAML_INVALID = "yaml-invalid"
    OCP_VERSION_PIN_MISSING = "ocp-version-pin-missing"
    FLEET_PIN_OVERRIDES_OCP_VERSIONS = "fleet-pin-overrides-ocp-versions"
    EMERGENCY_PIN = "emergency-pin"
    CLUSTER_POSITION_CONFLICT = "cluster-position-conflict"
    ENV_UNKNOWN = "env-unknown"
    CHART_REPO_ELSEWHERE = "chart-repo-elsewhere"
    CHART_VALUES_MISSING = "chart-values-missing"
    SYNC_DIFFERS = "sync-differs"


@dataclass(frozen=True, slots=True, order=True)
class Finding:
    """One problem: which rule, how bad, where, and what to do about it."""

    rule: Rule
    severity: Severity
    message: str
    team: str = ""
    path: str = ""
    cluster: str = ""
    chart: str = ""


def error(rule: Rule, message: str, **where: str) -> Finding:
    """An error finding."""
    return Finding(rule, Severity.ERROR, message, **where)


def warning(rule: Rule, message: str, **where: str) -> Finding:
    """A warning finding."""
    return Finding(rule, Severity.WARNING, message, **where)


def info(rule: Rule, message: str, **where: str) -> Finding:
    """An informational finding."""
    return Finding(rule, Severity.INFO, message, **where)
