"""Alerts, the dashboard, the runbook and the metric catalogue agree (ADR-0010).

server-scan's dashboard drifted from its chart (a threshold of 43200 against a
default of 21600) because nothing compared the two. These tests compare
every PromQL expression in the alert rules and the dashboard against the
metrics the code registers, and every alert against its runbook section.
Label values are checked too: a panel reading ``operation="start_upgrade"``
goes empty without an error if the code renames the operation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import (
    Dependency,
    GitLabOperation,
    Outcome,
    PlacementDecision,
    RolloutOutcome,
    RolloutTrigger,
    WingmanMetrics,
)
from wingman_day1.infrastructure.observed import (
    Day2Operation,
    HubOperation,
    OAuthOperation,
    SegmentsManagerOperation,
    ServerScanOperation,
    WorkflowsOperation,
)

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy/helm/wingman"
RULES = yaml.safe_load((CHART / "files/alerts.rules.yaml").read_text(encoding="utf-8"))
DASHBOARD: dict[str, Any] = json.loads(
    (CHART / "dashboards/wingman.json").read_text(encoding="utf-8")
)
RUNBOOK = (ROOT / "docs/ops/runbook.md").read_text(encoding="utf-8")

TARGET_LABELS = {"job", "instance", "namespace", "pod", "service"}

OPERATIONS: dict[str, set[str]] = {
    Dependency.GITLAB: set(GitLabOperation),
    Dependency.KUBERNETES: set(HubOperation),
    Dependency.OPENSHIFT_OAUTH: set(OAuthOperation),
    Dependency.DAY2: set(Day2Operation),
    Dependency.SERVER_SCAN: set(ServerScanOperation),
    Dependency.WORKFLOWS: set(WorkflowsOperation),
    Dependency.SEGMENTS_MANAGER: set(SegmentsManagerOperation),
}
"""Every ``operation`` value each ``dependency`` can carry."""

LABEL_VALUES: dict[str, set[str]] = {
    "dependency": set(Dependency),
    "outcome": {str(o) for o in (*Outcome, *RolloutOutcome)},
    "trigger": set(RolloutTrigger),
    "decision": set(PlacementDecision),
    "status_class": {"1xx", "2xx", "3xx", "4xx", "5xx", "other"},
}
"""The fixed values of every bounded label but ``operation``."""


def catalogue() -> dict[str, set[str]]:
    """Every series name the code can export, with its labels."""
    metrics = WingmanMetrics(CollectorRegistry(), component="t", version="0", commit="0")
    # One request and one GitLab call, so every family has a sample to read labels from.
    metrics.observe_http(method="GET", route="/x", status=200, seconds=0.1)
    metrics.observe_dependency(Dependency.GITLAB, GitLabOperation.READ_FILE, Outcome.OK, 0.1)
    metrics.observe_placement(PlacementDecision.PICKED)
    series: dict[str, set[str]] = {"up": set()}
    for family in metrics.registry.collect():
        labels = {label for sample in family.samples for label in sample.labels}
        names = {
            "counter": [f"{family.name}_total"],
            "histogram": [f"{family.name}_bucket", f"{family.name}_sum", f"{family.name}_count"],
        }.get(family.type, [family.name])
        for name in names:
            series[name] = (labels | {"le"}) if name.endswith("_bucket") else labels - {"le"}
    return series


def alert_rules() -> list[dict[str, Any]]:
    return [rule for group in RULES["groups"] for rule in group["rules"]]


def dashboard_exprs() -> list[str]:
    return [t["expr"] for p in DASHBOARD["panels"] for t in p.get("targets", [])]


def all_exprs() -> list[str]:
    return [rule["expr"] for rule in alert_rules()] + dashboard_exprs()


@pytest.mark.parametrize("expr", all_exprs())
def test_every_metric_and_label_in_an_expression_exists(expr: str) -> None:
    series = catalogue()
    for name, selector in re.findall(r"\b([a-z_:][a-z0-9_:]*)\s*\{([^}]*)\}", expr):
        assert name in series, f"{name} is not exported (expr: {expr})"
        for label in re.findall(r"([a-z_][a-z0-9_]*)\s*(?:=~|!~|!=|=)", selector):
            assert label in series[name] | TARGET_LABELS, f"{name} has no label {label}"
    bare = set(re.findall(r"\b(wingman_[a-z0-9_]+)\b", expr))
    assert bare <= set(series), f"unknown metrics {bare - set(series)} in {expr}"
    for group in re.findall(r"\bby\s*\(([^)]*)\)", expr):
        for label in (g.strip() for g in group.split(",")):
            known = set().union(*series.values()) | TARGET_LABELS
            assert label in known, f"grouping by unknown label {label} in {expr}"


def test_every_alert_has_a_runbook_section_and_every_section_an_alert() -> None:
    alerts = {rule["alert"] for rule in alert_rules()}
    sections = set(re.findall(r"^## (\w+)$", RUNBOOK, re.MULTILINE))
    assert alerts == sections
    for rule in alert_rules():
        assert rule["annotations"]["runbook"] == f"docs/ops/runbook.md#{rule['alert'].lower()}"
        assert rule["labels"]["severity"] in {"critical", "warning", "info"}
        assert {"summary", "description"} <= set(rule["annotations"])


def test_dashboard_panels_use_the_datasource_variable_and_the_job_filter() -> None:
    names = {v["name"] for v in DASHBOARD["templating"]["list"]}
    assert {"datasource", "job"} <= names
    ids = [p["id"] for p in DASHBOARD["panels"]]
    assert len(ids) == len(set(ids)), "panel ids must be unique"
    for panel in DASHBOARD["panels"]:
        assert panel["gridPos"]["x"] + panel["gridPos"]["w"] <= 24
        if panel["type"] == "row":
            continue
        assert panel["datasource"]["uid"] == "${datasource}", panel["title"]
        for target in panel["targets"]:
            assert 'job=~"$job"' in target["expr"], f"{panel['title']} ignores the job filter"


def test_dashboard_thresholds_quote_the_alert_thresholds() -> None:
    """A panel that names an alert must describe the alert's real threshold."""
    rules = {rule["alert"]: rule for rule in alert_rules()}
    for panel in DASHBOARD["panels"]:
        description = panel.get("description", "")
        for alert in re.findall(r"\b(Wingman[A-Za-z]+)\b", description):
            assert alert in rules, f"{panel['title']} names unknown alert {alert}"
            percent = re.search(r"Above (\d+)%", description)
            if percent:
                assert f"> {int(percent.group(1)) / 100:g}" in " ".join(
                    rules[alert]["expr"].split()
                ), f"{panel['title']} says {percent.group(1)}% but {alert} uses another threshold"


def label_matchers(expr: str) -> list[tuple[str, str, str]]:
    """Every ``label op "value"`` matcher in ``expr``, for the bounded labels."""
    labels = "dependency|operation|outcome|trigger|decision|status_class"
    return re.findall(rf'\b({labels})\s*(=~|!~|!=|=)\s*"([^"]*)"', expr)


def matches_some(pattern: str, op: str, known: set[str]) -> bool:
    """An exact value is one of ``known``; a regex matches at least one."""
    if op in {"=", "!="}:
        return pattern in known
    return any(re.fullmatch(pattern, value) for value in known)


@pytest.mark.parametrize("expr", all_exprs())
def test_every_label_value_in_an_expression_is_one_the_code_exports(expr: str) -> None:
    matchers = label_matchers(expr)
    dependencies = {v for label, op, v in matchers if label == "dependency" and op == "="}
    operations = set().union(*(OPERATIONS[d] for d in dependencies or OPERATIONS))
    for label, op, value in matchers:
        if "$" in value:  # a dashboard variable
            continue
        known = operations if label == "operation" else LABEL_VALUES[label]
        # Each alternative of a regex must name something, or the panel half reads nothing.
        for part in value.split("|") if op in {"=~", "!~"} else [value]:
            assert matches_some(part, op, known), f"{label} {op} {part!r} matches nothing: {expr}"


def test_every_dashboard_panel_says_what_it_shows_and_what_to_do() -> None:
    for panel in DASHBOARD["panels"]:
        if panel["type"] != "row":
            assert len(panel.get("description", "")) > 20, f"{panel['title']} has no description"


def test_dashboard_windows_are_grafanas_or_named_in_the_panel() -> None:
    """A fixed window (``[10m]``) is said in the title or description; the rest are Grafana's."""
    grafana = {"$__rate_interval", "$__interval", "$__range"}
    for panel in DASHBOARD["panels"]:
        text = f"{panel['title']} {panel.get('description', '')}"
        for target in panel.get("targets", []):
            for window in re.findall(r"\[([^\]]+)\]", target["expr"]):
                assert window in grafana or window in text, (
                    f"{panel['title']} reads a {window} window its text does not name"
                )
