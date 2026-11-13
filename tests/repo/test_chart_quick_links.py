"""The chart's Quick Links (ADR-0052): its settings, the links file's ConfigMap, day1's mounts.

The links file is mounted as a directory, so an edit reaches a running day1;
values reused from 3.8 (no ``quickLinks`` map) still render, leaving day1
its defaults, and so do values that still set what 3.13.1 removed (the
status checks and the ArgoCD tokens). day1 parses what the chart renders.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from wingman_day1.domain.quick_links import LinksFileState, parse_links_file
from wingman_day1.settings import Day1Settings

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy/helm/wingman"
FIXTURE = CHART / "ci/quick-links-values.yaml"

HELM = shutil.which("helm")
if HELM is None:
    if os.environ.get("CI"):
        raise RuntimeError("the chart's Quick Links tests need helm on PATH in CI")
    pytest.skip("helm is not installed", allow_module_level=True)


def render(*extra: str) -> dict[str, dict[str, Any]]:
    """Every rendered document, by kind and name."""
    assert HELM is not None
    rendered = subprocess.run(  # noqa: S603 - a fixed argv, no shell
        [HELM, "template", "wingman", str(CHART), "--namespace", "wingman", *extra],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {
        f"{doc['kind']}/{doc['metadata']['name']}": doc
        for doc in yaml.safe_load_all(rendered)
        if doc
    }


def config(*extra: str) -> dict[str, str]:
    return render(*extra)["ConfigMap/wingman-config"]["data"]


def day1_pod(*extra: str) -> dict[str, Any]:
    return render(*extra)["Deployment/wingman-day1"]["spec"]["template"]["spec"]


def test_the_defaults_reach_day1_and_day1_accepts_them() -> None:
    data = config()
    quick_links = {k: v for k, v in data.items() if k.startswith("QUICK_LINKS_")}
    assert quick_links == {
        "QUICK_LINKS_FILE": "/etc/wingman/quick-links/links.yaml",
        "QUICK_LINKS_HUB_NAME": "",
        "QUICK_LINKS_HUB_DOMAIN": "",
        "QUICK_LINKS_DOMAIN": "",
        "QUICK_LINKS_ARGOCD_URL_TEMPLATE": (
            "https://openshift-gitops-server-openshift-gitops.apps.{cluster}.{domain}"
        ),
        "QUICK_LINKS_CONSOLE_URL_TEMPLATE": (
            "https://console-openshift-console.apps.{cluster}.{domain}"
        ),
    }
    settings = Day1Settings(
        day1_gitlab_project_id="1",
        specs_gitlab_project_id="2",
        dev_auth_enabled=True,
        dev_auth_secret="s" * 32,
        **{k.lower(): v for k, v in quick_links.items()},  # ty: ignore[invalid-argument-type]
    )
    assert settings.quick_links_file == Path("/etc/wingman/quick-links/links.yaml")


def test_the_domain_defaults_to_the_mce_domain() -> None:
    data = config("--set", "clusterStatus.mceDomain=mgmt.example.internal")
    assert data["QUICK_LINKS_DOMAIN"] == "mgmt.example.internal"
    own = config(
        "--set",
        "clusterStatus.mceDomain=mgmt.example.internal",
        "--set",
        "quickLinks.domain=apps.example.internal",
    )
    assert own["QUICK_LINKS_DOMAIN"] == "apps.example.internal"


def test_values_kept_from_3_8_render_and_leave_day1_its_defaults() -> None:
    """``helm upgrade --reuse-values`` from 3.8 has no ``quickLinks`` map: the chart sets
    none of its variables (day1's defaults are the chart's), and the links file is empty."""
    kept = config("--set", "quickLinks=null")
    assert not [k for k in kept if k.startswith("QUICK_LINKS_")]
    links = render("--set", "quickLinks=null")["ConfigMap/wingman-quick-links"]["data"]
    assert yaml.safe_load(links["links.yaml"]) == {"sections": [], "clusters": {}}


def test_values_that_still_set_what_3_13_1_removed_render_and_are_ignored() -> None:
    """The status checks' and the ArgoCD tokens' keys (``--reuse-values`` from 3.9 to 3.13.0)."""
    old = [
        "--set",
        "quickLinks.status.enabled=false",
        "--set",
        "quickLinks.status.ttlSeconds=120",
        "--set",
        "quickLinks.status.timeoutSeconds=5",
        "--set",
        "quickLinks.status.concurrency=4",
        "--set",
        "quickLinks.sslVerify=false",
        "--set",
        "quickLinks.argocdTokensSecret=wingman-argocd-tokens",
    ]
    docs = render(*old)
    assert docs["ConfigMap/wingman-config"]["data"] == config()
    pod = docs["Deployment/wingman-day1"]["spec"]["template"]["spec"]
    assert pod == day1_pod()


def test_the_links_file_is_the_values_and_day1_reads_it_without_problems() -> None:
    docs = render("-f", str(FIXTURE))
    text = docs["ConfigMap/wingman-quick-links"]["data"]["links.yaml"]
    expected = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))["quickLinks"]
    assert yaml.safe_load(text) == {
        "sections": expected["sections"],
        "clusters": expected["clusters"],
    }
    parsed = parse_links_file(text)
    assert parsed.state is LinksFileState.LOADED
    assert parsed.problems == ()
    assert [s.name for s in parsed.sections] == ["Core GitOps"]


def test_day1_mounts_the_links_file_as_a_directory() -> None:
    pod = day1_pod("-f", str(FIXTURE))
    mounts = {m["name"]: m for m in pod["containers"][0]["volumeMounts"]}
    assert mounts == {
        "quick-links": {
            "name": "quick-links",
            "mountPath": "/etc/wingman/quick-links",
            "readOnly": True,
        }
    }  # no subPath: the kubelet updates it in place
    volumes = {v["name"]: v for v in pod["volumes"]}
    assert set(volumes) == {"quick-links"}
    assert volumes["quick-links"]["configMap"]["name"] == "wingman-quick-links"


def test_a_links_file_edit_does_not_restart_day1() -> None:
    """day1 re-reads the file, so the links ConfigMap is in no checksum annotation."""

    def annotations(*extra: str) -> dict[str, str]:
        deployment = render(*extra)["Deployment/wingman-day1"]
        return deployment["spec"]["template"]["metadata"]["annotations"]

    edited = ["--set", "quickLinks.sections[0].name=Tools"]
    edited += ["--set", "quickLinks.sections[0].links[0].name=Wiki"]
    edited += ["--set", "quickLinks.sections[0].links[0].url=https://wiki.example.internal"]
    assert set(annotations()) == {"checksum/config", "checksum/secret"}
    assert annotations(*edited) == annotations()
