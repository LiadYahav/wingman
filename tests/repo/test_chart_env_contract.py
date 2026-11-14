"""The chart sets exactly the variables the services read.

The legacy chart kept setting `GITLAB_ACCESS_TOKEN` after the core started
reading `GITLAB_TOKEN`, and a dozen `CACHE_*` names nothing read. Nothing
compared the two. These tests render the chart and compare the variables it
gives day1 and day2 (the keys of its ConfigMap and Secret, and the `env`
entries of the two services' Deployments, such as `SERVER_SCAN_TOKEN` from an
existing Secret) with the environment names of every settings class day1 and
day2 load (ADR-0009).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from wingman_core.settings import GitLabSettings
from wingman_day1.settings import Day1Settings

sys.path.insert(0, str(Path(__file__).parent))
from chart_render import render as render_chart
from chart_render import require_helm, template
from service_settings import env_names, read_by_services

# Read by libraries, not by a settings class: httpx's CA bundle.
LIBRARY_VARIABLES = {"SSL_CERT_FILE"}
# Set by the image (docs/ops/images.md), not by the chart.
IMAGE_VARIABLES = {"WINGMAN_VERSION", "WINGMAN_COMMIT"}
# Only for WINGMAN_GIT_BACKEND=fake, which production refuses.
FAKE_ONLY = {"WINGMAN_GIT_BACKEND", "WINGMAN_FIXTURES_DIR"}
# What both services load with envFrom.
SHARED = {"wingman-config", "wingman-secrets"}
# The services' Deployments, whose containers' `env` entries count too. The web's
# (NODE_ENV, for Next.js) is not one of them: no settings class reads it.
SERVICES = {"wingman-day1", "wingman-day2"}
# Every optional setting the chart sets with an `if`, and the values that turn it on.
ALL_ON = [
    arg
    for value in (
        "tls.caBundle=x",
        "clusterStatus.enabled=true",
        "serverScan.url=http://server-scan-api.wingman.svc:8000",
        "serverScan.uiUrl=https://server-scan.example",
        "serverScan.tokenSecret.name=server-scan-viewer",
        "workflows.url=http://workflows-orchestrator-api.wingman.svc:8080",
        "segmentsManager.url=http://segments-manager.wingman.svc:8000",
        "segmentsManager.uiUrl=https://segments-manager.example",
    )
    for arg in ("--set", value)
]

require_helm("the chart env contract tests")


def render(*extra: str) -> dict[str, dict[str, Any]]:
    """The rendered ConfigMap, Secret and service Deployments, by name."""
    docs = {
        doc["metadata"]["name"]: doc
        for doc in render_chart(*extra)
        if doc.get("metadata", {}).get("name") in SHARED | SERVICES
    }
    assert set(docs) == SHARED | SERVICES, f"the chart rendered only {sorted(docs)}"
    return docs


def service_env(*extra: str) -> dict[str, dict[str, dict[str, Any]]]:
    """Each service Deployment's `env` entries (all its containers'), by variable name."""
    entries: dict[str, dict[str, dict[str, Any]]] = {}
    for name, doc in render(*extra).items():
        if name in SERVICES:
            pod = doc["spec"]["template"]["spec"]
            containers = [*(pod.get("initContainers") or []), *pod["containers"]]
            entries[name] = {env["name"]: env for c in containers for env in c.get("env") or []}
    return entries


def chart_variables(*extra: str) -> set[str]:
    docs = render(*extra)
    keys: set[str] = set()
    for name in SHARED:
        keys |= set(docs[name].get("data") or {}) | set(docs[name].get("stringData") or {})
    assert keys, "the chart's wingman-config and wingman-secrets set nothing"
    for entries in service_env(*extra).values():
        keys |= set(entries)
    return keys


def test_every_variable_the_chart_sets_is_read_by_a_service() -> None:
    unread = chart_variables(*ALL_ON) - set(read_by_services()) - LIBRARY_VARIABLES
    assert not unread, f"the chart sets variables no settings class reads: {sorted(unread)}"


def test_every_required_setting_is_set_by_the_chart() -> None:
    required = {name for name, needed in read_by_services().items() if needed}
    missing = required - chart_variables() - IMAGE_VARIABLES - FAKE_ONLY
    assert not missing, f"required settings the chart never sets: {sorted(missing)}"


def test_the_gitlab_token_reaches_the_name_the_core_reads() -> None:
    assert "GITLAB_TOKEN" in env_names(GitLabSettings)
    assert "GITLAB_TOKEN" in chart_variables()


def test_the_server_scan_token_comes_from_its_secret_to_day1_only() -> None:
    assert "SERVER_SCAN_TOKEN" in env_names(Day1Settings)
    env = service_env(*ALL_ON)
    assert env["wingman-day1"]["SERVER_SCAN_TOKEN"] == {
        "name": "SERVER_SCAN_TOKEN",
        "valueFrom": {"secretKeyRef": {"name": "server-scan-viewer", "key": "token"}},
    }
    assert "SERVER_SCAN_TOKEN" not in env["wingman-day2"]
    assert "SERVER_SCAN_TOKEN" not in chart_variables(), "the token is set with server-scan off"


def test_the_server_scan_area_reads_with_the_viewer_token_and_its_own_keys() -> None:
    """The Server Scan area (ADR-0048) reads with the viewer token; its maintenance
    toggle (3.23.0) writes with the admin token, and a server's History (3.25.0)
    reads with the auditor token, each an optional key of the same Secret
    (docs/notes/2026-11-13-server-scan-area-api.md §4, §8.4, §9.5).
    """
    day1 = service_env(*ALL_ON)["wingman-day1"]
    secret_refs = {
        name: entry["valueFrom"]["secretKeyRef"]
        for name, entry in day1.items()
        if "secretKeyRef" in (entry.get("valueFrom") or {})
    }
    server_scan = {name for name in secret_refs if name.startswith("SERVER_SCAN_")}
    assert server_scan == {
        "SERVER_SCAN_TOKEN",
        "SERVER_SCAN_ADMIN_TOKEN",
        "SERVER_SCAN_AUDITOR_TOKEN",
    }
    assert {"SERVER_SCAN_ADMIN_TOKEN", "SERVER_SCAN_AUDITOR_TOKEN"} <= set(env_names(Day1Settings))
    assert secret_refs["SERVER_SCAN_ADMIN_TOKEN"] == {
        "name": "server-scan-viewer",
        "key": "admin-token",
        "optional": True,
    }, "a Secret without the admin key still starts day1"
    assert secret_refs["SERVER_SCAN_AUDITOR_TOKEN"] == {
        "name": "server-scan-viewer",
        "key": "auditor-token",
        "optional": True,
    }, "a Secret without the auditor key still starts day1"
    assert "optional" not in secret_refs["SERVER_SCAN_TOKEN"]
    day2 = service_env(*ALL_ON)["wingman-day2"]
    assert not {"SERVER_SCAN_ADMIN_TOKEN", "SERVER_SCAN_AUDITOR_TOKEN"} & set(day2)


@pytest.mark.parametrize(
    ("key", "variable"),
    [("adminKey", "SERVER_SCAN_ADMIN_TOKEN"), ("auditorKey", "SERVER_SCAN_AUDITOR_TOKEN")],
)
def test_the_admin_and_auditor_keys_can_be_left_out(key: str, variable: str) -> None:
    no_key = service_env(*ALL_ON, "--set", f"serverScan.tokenSecret.{key}=")["wingman-day1"]
    assert variable not in no_key
    assert "SERVER_SCAN_TOKEN" in no_key


def test_a_server_scan_with_auth_off_gets_no_token() -> None:
    pairs = [ALL_ON[i : i + 2] for i in range(0, len(ALL_ON), 2)]
    auth_off = [
        arg
        for pair in pairs
        if pair[1] != "serverScan.tokenSecret.name=server-scan-viewer"
        for arg in pair
    ]
    tokens = {"SERVER_SCAN_TOKEN", "SERVER_SCAN_ADMIN_TOKEN", "SERVER_SCAN_AUDITOR_TOKEN"}
    assert not tokens & set(service_env(*auth_off).get("wingman-day1", {})), (
        "a server-scan with auth off gets no token at all"
    )


def test_values_kept_from_a_release_before_3_4_still_render() -> None:
    """``helm upgrade --reuse-values`` from 3.3 has no ``serverScan``, ``workflows`` or
    ``segmentsManager`` map."""
    old = ["--set", "serverScan=null", "--set", "workflows=null", "--set", "segmentsManager=null"]
    prefixes = ("SERVER_SCAN_", "WORKFLOWS_", "SEGMENTS_MANAGER_")
    new = {v for v in chart_variables(*old) if v.startswith(prefixes)}
    assert not new
    reused = [
        *ALL_ON,
        *("--set", "serverScan.sslVerify=null", "--set", "serverScan.timeoutSeconds=null"),
        *("--set", "serverScan.tokenSecret.key=null", "--set", "workflows.timeoutSeconds=null"),
    ]
    config = render(*reused)["wingman-config"]["data"]
    assert config["SERVER_SCAN_SSL_VERIFY"] == "true"
    assert config["SERVER_SCAN_TIMEOUT_SECONDS"] == config["WORKFLOWS_TIMEOUT_SECONDS"] == "10"
    token = service_env(*reused)["wingman-day1"]["SERVER_SCAN_TOKEN"]
    assert token["valueFrom"]["secretKeyRef"]["key"] == "token"


def test_the_segments_manager_link_is_off_by_default_and_set_for_day1() -> None:
    assert "SEGMENTS_MANAGER_UI_URL" in env_names(Day1Settings)
    assert "SEGMENTS_MANAGER_UI_URL" not in chart_variables()
    config = render(*ALL_ON)["wingman-config"]["data"]
    assert config["SEGMENTS_MANAGER_UI_URL"] == "https://segments-manager.example"


def test_values_kept_from_3_4_still_render_segments_manager() -> None:
    """3.4's ``segmentsManager`` map has only ``uiUrl``: the link keeps working, the new
    keys take their defaults, and day1 calls nothing until ``url`` is set."""
    link = ["--set", "segmentsManager.uiUrl=https://segments-manager.example"]
    config = render(*link)["wingman-config"]["data"]
    assert {v for v in config if v.startswith("SEGMENTS_MANAGER_")} == {"SEGMENTS_MANAGER_UI_URL"}
    reused = [
        *link,
        *("--set", "segmentsManager.url=http://segments-manager.wingman.svc:8000"),
        *("--set", "segmentsManager.sslVerify=null"),
        *("--set", "segmentsManager.timeoutSeconds=null"),
    ]
    config = render(*reused)["wingman-config"]["data"]
    assert config["SEGMENTS_MANAGER_URL"] == "http://segments-manager.wingman.svc:8000"
    assert config["SEGMENTS_MANAGER_SSL_VERIFY"] == "true"
    assert config["SEGMENTS_MANAGER_TIMEOUT_SECONDS"] == "5"


def test_placement_needs_70_free_pods_unless_set_also_for_values_kept_from_3_7() -> None:
    """ADR-0050: values kept with ``--reuse-values`` from a release before placement have
    no ``day1.placementMinFreePods``; day1 must still get a number, and 0 stays 0."""
    assert render()["wingman-config"]["data"]["PLACEMENT_MIN_FREE_PODS"] == "70"
    kept = render("--set", "day1.placementMinFreePods=null")["wingman-config"]["data"]
    assert kept["PLACEMENT_MIN_FREE_PODS"] == "70"
    for value in ("0", "120"):
        on = render("--set", f"day1.placementMinFreePods={value}")["wingman-config"]["data"]
        assert on["PLACEMENT_MIN_FREE_PODS"] == value


def test_creates_open_merge_requests_unless_the_workflow_is_chosen() -> None:
    """ADR-0042: ``day1.provisioner`` defaults to merge-request, also for values kept from
    3.6 that have no such key; ``workflow`` needs ``workflows.url``."""
    assert render()["wingman-config"]["data"]["DAY1_PROVISIONER"] == "merge-request"
    kept = render("--set", "day1.provisioner=null")["wingman-config"]["data"]
    assert kept["DAY1_PROVISIONER"] == "merge-request"
    on = render(*ALL_ON, "--set", "day1.provisioner=workflow")["wingman-config"]["data"]
    assert on["DAY1_PROVISIONER"] == "workflow"
    refused = template("--set", "day1.provisioner=workflow")
    assert refused.returncode != 0
    assert "day1.provisioner workflow needs workflows.url" in refused.stderr


def test_upgrades_are_off_unless_turned_on_also_for_values_kept_from_3_15() -> None:
    """ADR-0055: ``day1.upgrades.enabled`` defaults to off, also for values kept from a
    release before it (no ``day1.upgrades`` map); on needs ``workflows.url``, and the
    targets read gets its own timeout, 65 s unless set."""
    assert render()["wingman-config"]["data"]["DAY1_UPGRADES"] == "false"
    kept = render("--set", "day1.upgrades=null")["wingman-config"]["data"]
    assert kept["DAY1_UPGRADES"] == "false"
    on = render(*ALL_ON, "--set", "day1.upgrades.enabled=true")["wingman-config"]["data"]
    assert on["DAY1_UPGRADES"] == "true"
    assert on["WORKFLOWS_TARGETS_TIMEOUT_SECONDS"] == "65"
    reused = render(*ALL_ON, "--set", "workflows.targetsTimeoutSeconds=null")
    assert reused["wingman-config"]["data"]["WORKFLOWS_TARGETS_TIMEOUT_SECONDS"] == "65"
    refused = template("--set", "day1.upgrades.enabled=true")
    assert refused.returncode != 0
    assert "day1.upgrades.enabled needs workflows.url" in refused.stderr


def test_adding_servers_is_off_unless_enabled_and_needs_the_orchestrator() -> None:
    """ADR-0057: ``day1.addServers.enabled`` sets DAY1_ADD_SERVERS, also off for values kept
    from 3.17 that have no such key; on, it needs ``workflows.url``."""
    assert render()["wingman-config"]["data"]["DAY1_ADD_SERVERS"] == "false"
    kept = render("--set", "day1.addServers=null")["wingman-config"]["data"]
    assert kept["DAY1_ADD_SERVERS"] == "false"
    on = render(*ALL_ON, "--set", "day1.addServers.enabled=true")["wingman-config"]["data"]
    assert on["DAY1_ADD_SERVERS"] == "true"
    refused = template("--set", "day1.addServers.enabled=true")
    assert refused.returncode != 0
    assert "day1.addServers.enabled needs workflows.url" in refused.stderr
