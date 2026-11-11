"""``GET /api/day1/machine-configs`` over HTTP, in the shape the web's config picker reads."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

Auth = Callable[[User], dict[str, str]]
URL = "/api/day1/machine-configs"


async def test_the_catalogue_and_defaults_from_the_fixture_repos(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await client.get(URL, headers=auth(support.VIEWER))
    assert response.status_code == 200, response.text
    assert response.json() == {
        "network_config": "nm-conf",
        "static_configs": [
            {"name": "nic-ring-buffer", "folder": "", "path": "mc-files/nic-ring-buffer.bu"},
            {
                "name": "worker-kubeletconfig-reserved",
                "folder": "",
                "path": "mc-files/worker-kubeletconfig-reserved",
            },
            {
                "name": "workers-chrony-configuration",
                "folder": "",
                "path": "mc-files/workers-chrony-configuration.bu",
            },
            {
                "name": "kubevirt-worker-tuning",
                "folder": "kubevirt",
                "path": "mc-files/kubevirt/kubevirt-worker-tuning.bu",
            },
        ],
        "hardware_types": [
            {"name": hw, "template": f"mc-files/templates/nm-conf-template-{hw}.bu"}
            for hw in ("cisco", "dell", "dell-data")
        ],
        "nodepool_defaults": {
            "path": "nodepool-defaults.yaml",
            "found": True,
            "configs": [
                {"name": "nm-conf"},
                {"name": "workers-chrony-configuration"},
                {"name": "nic-ring-buffer"},
            ],
            "error": None,
            "problems": [],
        },
        "problems": [],
    }


async def test_a_broken_defaults_file_is_served_with_its_error(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.push(
        gitlab, support.SPECS, branch="main", file="nodepool-defaults.yaml", content="- x\n"
    )
    body = (await client.get(URL, headers=auth(support.VIEWER))).json()
    assert body["nodepool_defaults"] == {
        "path": "nodepool-defaults.yaml",
        "found": True,
        "configs": [],
        "error": "nodepool-defaults.yaml is not a YAML mapping",
        "problems": [],
    }
    assert body["static_configs"]  # the catalogue is still served


async def test_reading_the_catalogue_needs_a_session(client: httpx.AsyncClient) -> None:
    response = await client.get(URL)
    assert (response.status_code, response.json()["code"]) == (401, "UNAUTHORIZED")
