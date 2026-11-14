"""Every pod the chart renders runs as OpenShift's restricted-v2 SCC expects.

The set is herzi's and server-scan's (convention 1): pod ``runAsNonRoot`` and
the RuntimeDefault seccomp profile, no ``runAsUser``; each container without
privilege escalation or capabilities and with a read-only root; an emptyDir
only where a process writes; no service-account token. Every image is pinned
(no ``latest``; nginx by digest), and no NetworkPolicy is ever rendered
(convention 15). Checked on every ``ci/`` fixture and with every optional
template on.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from chart_render import CHART, render, require_helm

require_helm("the chart's hardening tests")

FIXTURES = sorted(CHART.glob("ci/*.yaml"))
# Every template an `if` guards, on at once.
ALL_ON = [
    arg
    for value in (
        "tls.caBundle=x",
        "clusterStatus.enabled=true",
        "serverScan.url=http://server-scan-api.wingman.svc:8000",
        "serverScan.tokenSecret.name=server-scan-viewer",
        "workflows.url=http://workflows-orchestrator-api.wingman.svc:8080",
        "segmentsManager.url=http://segments-manager.wingman.svc:8000",
        "day1.upgrades.enabled=true",
        "ingress.enabled=true",
        "monitoring.serviceMonitor.enabled=true",
        "monitoring.prometheusRule.enabled=true",
        "monitoring.grafanaDashboard.enabled=true",
    )
    for arg in ("--set", value)
]
RENDERS = {
    **{fixture.name: ("-f", str(fixture)) for fixture in FIXTURES},
    "every template on": tuple(ALL_ON),
}
POD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "ReplicaSet"}
# The only paths a process writes (docs/ops/images.md, "Read-only root").
WRITABLE = {
    "wingman-day1": set(),
    "wingman-day2": set(),
    "wingman-web": {"/app/apps/web/.next/cache"},
    "wingman-nginx": {"/tmp"},  # noqa: S108 - nginx's emptyDir in the pod, no file of ours
}


def pods(*extra: str) -> dict[str, dict[str, Any]]:
    """Each workload's pod spec, by workload name."""
    docs = render(*extra)
    specs = {
        d["metadata"]["name"]: d["spec"]["template"]["spec"] for d in docs if d["kind"] in POD_KINDS
    }
    assert not [d for d in docs if d["kind"] == "CronJob"], (
        "a CronJob's pods would need checking too"
    )
    return specs


def containers(pod: dict[str, Any]) -> list[dict[str, Any]]:
    return [*(pod.get("initContainers") or []), *pod["containers"]]


@pytest.mark.parametrize("extra", RENDERS.values(), ids=RENDERS.keys())
def test_every_pod_is_non_root_with_seccomp_and_no_assigned_uid(extra: tuple[str, ...]) -> None:
    rendered = pods(*extra)
    assert set(rendered) == set(WRITABLE)
    for name, pod in rendered.items():
        context = pod["securityContext"]
        assert context == {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}}, name
        # OpenShift assigns the UID and the group from the namespace's range.
        for container in containers(pod):
            assert not {"runAsUser", "runAsGroup"} & set(container["securityContext"]), name


@pytest.mark.parametrize("extra", RENDERS.values(), ids=RENDERS.keys())
def test_every_container_drops_everything_and_has_a_read_only_root(extra: tuple[str, ...]) -> None:
    for name, pod in pods(*extra).items():
        for container in containers(pod):
            assert container["securityContext"] == {
                "allowPrivilegeEscalation": False,
                "capabilities": {"drop": ["ALL"]},
                "readOnlyRootFilesystem": True,
            }, f"{name}/{container['name']}"


@pytest.mark.parametrize("extra", RENDERS.values(), ids=RENDERS.keys())
def test_no_pod_mounts_a_service_account_token(extra: tuple[str, ...]) -> None:
    """Nothing reads the Kubernetes API with the pod's token (day1's MCE reads use the Secret's)."""
    for name, pod in pods(*extra).items():
        assert pod["automountServiceAccountToken"] is False, name


@pytest.mark.parametrize("extra", RENDERS.values(), ids=RENDERS.keys())
def test_only_the_paths_a_process_writes_are_writable(extra: tuple[str, ...]) -> None:
    for name, pod in pods(*extra).items():
        volumes = {v["name"]: v for v in pod.get("volumes") or []}
        mounts = [m for c in containers(pod) for m in c.get("volumeMounts") or []]
        empty = {m["mountPath"] for m in mounts if "emptyDir" in volumes[m["name"]]}
        assert empty == WRITABLE[name], name
        for mount in mounts:
            if "emptyDir" in volumes[mount["name"]]:
                assert volumes[mount["name"]]["emptyDir"].get("sizeLimit"), mount
            else:
                assert mount.get("readOnly") is True, f"{name}: {mount}"


@pytest.mark.parametrize("extra", RENDERS.values(), ids=RENDERS.keys())
def test_no_image_is_latest_and_nginx_is_pinned_by_digest(extra: tuple[str, ...]) -> None:
    for name, pod in pods(*extra).items():
        for container in containers(pod):
            image = container["image"]
            reference = image.split("@")[0]
            tag = reference.rsplit(":", 1)[1] if ":" in reference.rsplit("/", 1)[-1] else ""
            assert tag, f"{name}: {image} names no tag"
            assert tag != "latest", f"{name}: {image}"
    nginx = containers(pods(*extra)["wingman-nginx"])[0]["image"]
    assert "@sha256:" in nginx


@pytest.mark.parametrize("extra", RENDERS.values(), ids=RENDERS.keys())
def test_no_network_policy_is_ever_rendered(extra: tuple[str, ...]) -> None:
    """Convention 15: network policies caused connectivity issues; neither exemplar ships one."""
    assert not [d for d in render(*extra) if d["kind"] == "NetworkPolicy"]


def test_no_template_can_render_a_network_policy() -> None:
    templates = sorted((CHART / "templates").iterdir())
    assert not [t.name for t in templates if "NetworkPolicy" in t.read_text(encoding="utf-8")]
