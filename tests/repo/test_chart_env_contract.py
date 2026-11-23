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
# A development install without the orchestrator: the one place the chart allows none.
NO_ORCHESTRATOR = ["--set", "environment=development", "--set", "workflows.url="]
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


def test_day1_reads_server_scan_with_the_viewer_token_only() -> None:
    """One viewer token, from the Secret, for every read (ADR-0038). The admin and auditor
    tokens went with the Server Scan area (removed in 3.52.1): their keys render nothing."""
    with_keys = (
        "--set",
        "serverScan.tokenSecret.adminKey=admin-token",
        "--set",
        "serverScan.tokenSecret.auditorKey=auditor-token",
    )
    for extra in ((), with_keys):
        day1 = service_env(*ALL_ON, *extra)["wingman-day1"]
        secret_refs = {
            name: entry["valueFrom"]["secretKeyRef"]
            for name, entry in day1.items()
            if "secretKeyRef" in (entry.get("valueFrom") or {})
        }
        assert {name for name in secret_refs if name.startswith("SERVER_SCAN_")} == {
            "SERVER_SCAN_TOKEN"
        }
        assert "optional" not in secret_refs["SERVER_SCAN_TOKEN"]
    assert not {"SERVER_SCAN_ADMIN_TOKEN", "SERVER_SCAN_AUDITOR_TOKEN"} & set(
        env_names(Day1Settings)
    )
    assert "SERVER_SCAN_TOKEN" not in service_env(*ALL_ON)["wingman-day2"]


def test_a_server_scan_with_auth_off_gets_no_token() -> None:
    pairs = [ALL_ON[i : i + 2] for i in range(0, len(ALL_ON), 2)]
    auth_off = [
        arg
        for pair in pairs
        if pair[1] != "serverScan.tokenSecret.name=server-scan-viewer"
        for arg in pair
    ]
    assert "SERVER_SCAN_TOKEN" not in service_env(*auth_off).get("wingman-day1", {}), (
        "a server-scan with auth off gets no token at all"
    )


def test_values_kept_from_a_release_before_3_4_still_render() -> None:
    """``helm upgrade --reuse-values`` from 3.3 has no ``serverScan``, ``workflows`` or
    ``segmentsManager`` map: production needs ``workflows.url`` now (ADR-0042), so they
    fail naming it, and render in development."""
    old = ["--set", "serverScan=null", "--set", "workflows=null", "--set", "segmentsManager=null"]
    refused = template(*old)
    assert refused.returncode != 0
    assert "workflows.url is required" in refused.stderr
    prefixes = ("SERVER_SCAN_", "WORKFLOWS_", "SEGMENTS_MANAGER_")
    new = {
        v
        for v in chart_variables(*old, "--set", "environment=development")
        if v.startswith(prefixes)
    }
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


def test_creates_need_the_orchestrator_and_the_dropped_provisioner_changes_nothing() -> None:
    """ADR-0042, amended 2026-11-23: every create starts provision-cluster, so the chart
    refuses an empty ``workflows.url`` outside development; ``day1.provisioner`` (3.7.0 to
    3.53), any value, renders nothing and nothing reads DAY1_PROVISIONER."""
    config = render()["wingman-config"]["data"]
    assert config["WORKFLOWS_API_URL"] == "http://workflows-orchestrator-api.ns.svc:8080"
    refused = template("--set", "workflows.url=")
    assert refused.returncode != 0
    assert "workflows.url is required" in refused.stderr
    assert "WORKFLOWS_API_URL" not in render(*NO_ORCHESTRATOR)["wingman-config"]["data"]
    for value in ("merge-request", "workflow", "null"):
        assert render("--set", f"day1.provisioner={value}") == render()
    assert "DAY1_PROVISIONER" not in config
    assert "DAY1_PROVISIONER" not in env_names(Day1Settings)


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
    refused = template(*NO_ORCHESTRATOR, "--set", "day1.upgrades.enabled=true")
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
    refused = template(*NO_ORCHESTRATOR, "--set", "day1.addServers.enabled=true")
    assert refused.returncode != 0
    assert "day1.addServers.enabled needs workflows.url" in refused.stderr


def scale(*extra: str) -> str:
    return render(*extra)["wingman-config"]["data"]["DAY1_SCALE_NODEPOOLS"]


def test_scaling_nodepools_is_on_by_default_wherever_the_orchestrator_is() -> None:
    """ADR-0062's 2026-11-23 amendment: ``day1.scaleNodepools.enabled`` is true by default, and
    DAY1_SCALE_NODEPOOLS is on wherever ``workflows.url`` is set, also for values kept from a
    release before 3.40 that have no such key; false turns it off. Without ``workflows.url``
    (development only, ADR-0042) there is no Scale and nothing fails, whatever the value
    says. Not a boolean, the schema refuses it."""
    assert scale(*ALL_ON) == "true"
    assert scale() == "true", "the default install has the orchestrator it requires"
    assert scale(*ALL_ON, "--set", "day1.scaleNodepools=null") == "true"
    assert scale(*ALL_ON, "--set", "day1.scaleNodepools.enabled=true") == "true"
    assert scale(*ALL_ON, "--set", "day1.scaleNodepools.enabled=false") == "false"
    assert scale(*NO_ORCHESTRATOR) == "false", "development without the orchestrator: no Scale"
    assert scale(*NO_ORCHESTRATOR, "--set", "day1.scaleNodepools.enabled=true") == "false"
    assert scale(*NO_ORCHESTRATOR, "--set", "day1.scaleNodepools=null") == "false"
    for empty in (("--set", "workflows=null"), ("--set", "workflows.url=")):
        development = ("--set", "environment=development", *empty)
        assert template(*development).returncode == 0
        assert scale(*development) == "false"
    wrong = template(*ALL_ON, "--set-string", "day1.scaleNodepools.enabled=yes")
    assert wrong.returncode != 0
    assert "scaleNodepools" in wrong.stderr


def test_multi_infraenv_nodepools_are_off_unless_enabled() -> None:
    """ADR-0064: ``day1.multiInfraEnvNodepools.enabled`` sets DAY1_MULTI_INFRAENV_NODEPOOLS, also
    off for values kept from a release before it; it needs nothing else; not a boolean, the
    schema refuses it."""
    assert render()["wingman-config"]["data"]["DAY1_MULTI_INFRAENV_NODEPOOLS"] == "false"
    kept = render("--set", "day1.multiInfraEnvNodepools=null")["wingman-config"]["data"]
    assert kept["DAY1_MULTI_INFRAENV_NODEPOOLS"] == "false"
    on = render("--set", "day1.multiInfraEnvNodepools.enabled=true")["wingman-config"]["data"]
    assert on["DAY1_MULTI_INFRAENV_NODEPOOLS"] == "true"
    wrong = template("--set-string", "day1.multiInfraEnvNodepools.enabled=yes")
    assert wrong.returncode != 0
    assert "multiInfraEnvNodepools" in wrong.stderr


@pytest.mark.parametrize("key", ["serverScanRefresh", "segmentsArea", "serverScanArea"])
def test_the_removed_areas_switches_are_accepted_and_render_nothing(key: str) -> None:
    """The Segments and Server Scan areas were removed in 3.52.1 (ADR-0066):
    ``day1.<key>.enabled`` renders no variable, needs no system's url, and changes nothing."""
    for base in ((), tuple(ALL_ON)):
        on = render(*base, "--set", f"day1.{key}.enabled=true")
        assert on == render(*base)
    variables = {"DAY1_SERVER_SCAN_REFRESH", "DAY1_SEGMENTS_AREA", "DAY1_SERVER_SCAN_AREA"}
    assert not variables & set(render()["wingman-config"]["data"])
    assert not variables & set(env_names(Day1Settings))


def test_excluded_agent_labels_are_label_keys_joined_with_commas() -> None:
    """ADR-0065: ``day1.excludedAgentLabels`` sets DAY1_EXCLUDED_AGENT_LABELS, empty by default
    and for values kept from a release before it; each must be a label key, at most 16."""
    assert render()["wingman-config"]["data"]["DAY1_EXCLUDED_AGENT_LABELS"] == ""
    kept = render("--set", "day1.excludedAgentLabels=null")["wingman-config"]["data"]
    assert kept["DAY1_EXCLUDED_AGENT_LABELS"] == ""
    on = render("--set-json", 'day1.excludedAgentLabels=["redbull.io/used","used-by-herzi"]')
    assert (
        on["wingman-config"]["data"]["DAY1_EXCLUDED_AGENT_LABELS"]
        == "redbull.io/used,used-by-herzi"
    )
    for wrong in ('["not a key"]', '["Redbull.IO/used"]', '"redbull.io/used"', '["a","a"]'):
        refused = template("--set-json", f"day1.excludedAgentLabels={wrong}")
        assert refused.returncode != 0, wrong
        assert "excludedAgentLabels" in refused.stderr, wrong


TLS_VERIFY = {
    "auth.sslVerify": "OPENSHIFT_SSL_VERIFY",
    "clusterStatus.sslVerify": "MCE_SSL_VERIFY",
    "serverScan.sslVerify": "SERVER_SCAN_SSL_VERIFY",
    "workflows.sslVerify": "WORKFLOWS_SSL_VERIFY",
    "segmentsManager.sslVerify": "SEGMENTS_MANAGER_SSL_VERIFY",
}


@pytest.mark.parametrize(("key", "variable"), TLS_VERIFY.items())
@pytest.mark.parametrize(
    ("flag", "value", "expected"),
    [
        ("--set", "false", "false"),  # a boolean: before 3.33 three keys turned it into "true"
        ("--set-string", "false", "false"),
        ("--set", "true", "true"),
        ("--set", "/etc/pki/ca-trust/internal.pem", "/etc/pki/ca-trust/internal.pem"),
        ("--set", "null", "true"),  # unset, as values kept from before the key
    ],
    ids=["false", "string false", "true", "a CA path", "unset"],
)
def test_every_tls_setting_takes_a_boolean_a_string_or_nothing(
    key: str, variable: str, flag: str, value: str, expected: str
) -> None:
    """``wingman.tlsVerify`` renders all five the same way (ADR-0059)."""
    assert variable in read_by_services()
    config = render(*ALL_ON, flag, f"{key}={value}")["wingman-config"]["data"]
    assert config[variable] == expected
