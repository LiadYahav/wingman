"""The fixture template, rendered for a new cluster, satisfies the day1 values contract.

``dev/gitlab-fixtures/wingman/cluster-specs/cluster-template.j2`` is the
reference template. Rendering it through the real create path (preview) must
give exactly the keys a person or portal may write (ADR-0012). When ``helm``
is installed and ``WINGMAN_TEST_CHART_DIR`` points at a hostedclusters-setup
chart, the file is also rendered with the ApplicationSet's value layers.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.clusters import CreateCluster

NAME = "ocp4-prod-falcon-site1"
SITE = "site1"
MCE = "ocp4-prod-mce-site1-a"
FORBIDDEN = {"vlanId", "dhcp_values", "mcFiles", "mcConfigMap", "clusterName", "site", "mce"}

NODEPOOLS = [
    {
        "infra_env": "dell-r660-site1-128c-1024gb-5tb",
        "nodepool_name": "falcon-zone-a",
        "replicas": 3,
        "configs": [{"name": "worker-kubeletconfig-reserved"}, {"name": "nic-ring-buffer"}],
        "node_labels": {"topology.kubernetes.io/zone": "a"},
        "tuning_config": "tuned-performance",
    },
    {
        "infra_env": "hp-gen11-site1-64c",
        "replicas": 0,
        "configs": [{"name": "worker-kubeletconfig-reserved"}],
    },
]


def create(**variables: Any) -> CreateCluster:
    return CreateCluster(
        name=NAME,
        site=SITE,
        mce=MCE,
        spec_name="agent-standard",
        spec_version="1.0.0",
        variables={
            "owner_merkaz": "1234",
            "owner_anaf": "56",
            "owner_mador": "7",
            "openshift_release_version": "4.18.22-x86_64",
            "nodepools": NODEPOOLS,
            **variables,
        },
        addon_overrides={"redbull/cluster-roles": {"rbac": {"admins": ["alice"]}}},
    )


async def test_a_rendered_agent_cluster_has_only_the_keys_people_write(
    context: Day1Context,
) -> None:
    rendered = await context.clusters.preview(create())
    documents = list(yaml.safe_load_all(rendered.content))
    assert len(documents) == 1
    values = documents[0]
    assert isinstance(values, dict)
    assert set(values) == {"owner", "mastertag", "nodepool"}
    assert not FORBIDDEN & set(values)
    assert values["owner"] == {"merkaz": "1234", "anaf": "56", "mador": "7"}
    assert all(isinstance(v, str) for v in values["owner"].values())
    assert values["mastertag"] == "4.18.22-x86_64"
    zone_a, spare = values["nodepool"]
    assert zone_a == {
        "infraEnvName": "dell-r660-site1-128c-1024gb-5tb",
        "name": "falcon-zone-a",
        "replicas": 3,
        "labels": {"allowDeletion": False},
        "configs": [{"name": "worker-kubeletconfig-reserved"}, {"name": "nic-ring-buffer"}],
        "nodeLabels": {"topology.kubernetes.io/zone": "a"},
        "tuningConfig": "tuned-performance",
    }
    assert spare == {
        "infraEnvName": "hp-gen11-site1-64c",
        "replicas": 0,
        "labels": {"allowDeletion": False},
        "configs": [{"name": "worker-kubeletconfig-reserved"}],
    }
    assert all(isinstance(pool["replicas"], int) for pool in values["nodepool"])


async def test_a_rendered_file_starts_with_the_provenance_header(context: Day1Context) -> None:
    rendered = await context.clusters.preview(create())
    header = rendered.content.splitlines()[:3]
    assert header[0] == '# specName: "agent-standard"'
    assert header[1] == '# specVersion: "1.0.0"'
    assert header[2].startswith("# wingmanAddons: ")
    assert '"rbac": {"admins": ["alice"]}' in header[2]


async def test_a_kubevirt_cluster_renders_the_platform_key(context: Day1Context) -> None:
    rendered = await context.clusters.preview(create(platform="kubevirt"))
    values = yaml.safe_load(rendered.content)
    assert values["platform"] == "kubevirt"
    assert set(values) == {"owner", "mastertag", "platform", "nodepool"}


async def test_replicas_default_to_two_when_the_form_leaves_them_out(
    context: Day1Context,
) -> None:
    pools = [{"infra_env": "dell-r660-site1-128c-1024gb-5tb"}]
    values = yaml.safe_load((await context.clusters.preview(create(nodepools=pools))).content)
    assert values["nodepool"] == [
        {
            "infraEnvName": "dell-r660-site1-128c-1024gb-5tb",
            "replicas": 2,
            "labels": {"allowDeletion": False},
        }
    ]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)  # noqa: S603 - a fixed argv, no shell


def _chart_dir() -> Path:
    if shutil.which("helm") is None:
        pytest.skip("helm is not installed")
    chart = os.environ.get("WINGMAN_TEST_CHART_DIR", "")
    if not chart or not (Path(chart) / "Chart.yaml").is_file():
        pytest.skip("set WINGMAN_TEST_CHART_DIR to a hostedclusters-setup chart to run helm")
    return Path(chart)


async def test_the_rendered_file_renders_through_the_chart(
    context: Day1Context, tmp_path: Path
) -> None:
    chart = _chart_dir()
    helm = shutil.which("helm")
    assert helm is not None
    rendered = await context.clusters.preview(create())
    cluster_file = tmp_path / f"{NAME}.yaml"
    cluster_file.write_text(rendered.content, encoding="utf-8")
    sites = default_fixture_root() / "gitops-day1" / "platform-config" / "sites"
    layers = [
        sites / "configValues.yaml",
        sites / SITE / "values.yaml",
        sites / SITE / "mces" / MCE / "values.yaml",
        cluster_file,
    ]
    command = [helm, "template", NAME, str(chart)]
    for layer in layers:
        command += ["-f", str(layer)]
    command += [
        "--set-string",
        f"clusterName={NAME},site={SITE},mce={MCE}",
        "--set",
        "hostedCluster.enabled=true",
    ]
    result = await asyncio.to_thread(_run, command)
    assert result.returncode == 0, result.stderr
    objects = [o for o in yaml.safe_load_all(result.stdout) if isinstance(o, dict)]
    kinds = [o.get("kind") for o in objects]
    assert "HostedCluster" in kinds
    node_pools = sorted(o["metadata"]["name"] for o in objects if o.get("kind") == "NodePool")
    assert node_pools == ["falcon-zone-a", f"{NAME}-hp-gen11-site1-64c"]
