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

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from wingman_core.settings import GitLabSettings
from wingman_day1.settings import Day1Settings

sys.path.insert(0, str(Path(__file__).parent))
from service_settings import env_names, read_by_services

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy/helm/wingman"
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
    )
    for arg in ("--set", value)
]

HELM = shutil.which("helm")
if HELM is None:
    if os.environ.get("CI"):
        raise RuntimeError("the chart env contract needs helm on PATH in CI")
    pytest.skip("helm is not installed", allow_module_level=True)


def render(*extra: str) -> dict[str, dict[str, Any]]:
    """The rendered ConfigMap, Secret and service Deployments, by name."""
    assert HELM is not None
    rendered = subprocess.run(  # noqa: S603 - a fixed argv, no shell
        [HELM, "template", "wingman", str(CHART), "--namespace", "wingman", *extra],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    docs = {
        doc["metadata"]["name"]: doc
        for doc in yaml.safe_load_all(rendered)
        if doc and doc.get("metadata", {}).get("name") in SHARED | SERVICES
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
