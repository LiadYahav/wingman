"""Creating a KV cluster on a seed through provision-cluster, over HTTP (ADR-0069).

The fixtures' seed ``ocp4-prod-seed-site1-az1-a`` (default mastertag
``4.18.22-x86_64``, which its ladder does not offer) holds ``-a`` and ``-b``,
each one NodePool from ``r760-mtl-az1``; the conftest's hub has no access to
the seed, so its InfraEnvs are the ones those files name.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx

from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import ProvisionRefusedError
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_provision import FakeProvisionWorkflow

Auth = Callable[[User], dict[str, str]]
SEED = "ocp4-prod-seed-site1-az1-a"
DRAFT = f"/api/day1/seeds/{SEED}/kv-cluster-draft"
CREATE = f"/api/day1/seeds/{SEED}/kv-clusters"
NEXT = "ocp4-prod-kv-site1-az1-c"
KV_FILES = [f"sites/site1/mces/{SEED}/hostedClusters/ocp4-prod-kv-site1-az1-{x}.yaml" for x in "ab"]
EXPECTED = """\
owner:
  merkaz: "1000"
  anaf: "10"
  mador: "1"

mastertag: 4.18.56

nodepool:
  - infraEnvName: r760-mtl-az1
    replicas: 3
    labels:
      allowDeletion: false
    configs:
      - name: workers-chrony-configuration
      - name: kubevirt-worker-tuning
    nodeLabels: {"topology.kubernetes.io/zone": "az1"}
"""


@asynccontextmanager
async def client_with(
    support: Any, gitlab: InMemoryGitLab, clock: Any, **app: Any
) -> AsyncIterator[Any]:
    """A client of an app built on ``gitlab`` with the given hub."""
    built = support.build_app(
        gitlab=gitlab, identity=None, day2=FakeDay2Addons(), clock=clock, **app
    )
    transport = httpx.ASGITransport(app=built)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        yield client


# ── The draft ────────────────────────────────────────────────────────────────


async def test_the_draft_fills_the_next_kv_cluster_from_the_seed_and_its_newest(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await client.get(DRAFT, headers=auth(support.ALICE))
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft == draft | {
        "seed": SEED,
        "site": "site1",
        "name": NEXT,  # -a and -b are taken: the lowest free id (acceptance P10)
        "zone": "az1",
        "zones": ["az1"],
        "mastertag": "4.18.56",  # its default 4.18.22 is no rung: the newest it offers
        "versions": ["4.18.56", "4.17.58", "4.16.55"],
        "infra_env": "r760-mtl-az1",
        "infra_envs": ["r760-mtl-az1"],
        "infra_envs_from": "files",
        "workers": 3,
        "default_workers": 3,
        "max_workers": 40,
        "standby_workers": [1, 5],
        "owner": {"merkaz": "1000", "anaf": "10", "mador": "1"},
        "path": f"sites/site1/mces/{SEED}/hostedClusters/{NEXT}.yaml",
        "yaml": EXPECTED,
        "problems": [],
    }
    assert draft["model"] == {
        "name": "ocp4-prod-kv-site1-az1-b",  # the newest on the seed, by its id letter
        "site": "site1",
        "seed": SEED,
        "configs": ["workers-chrony-configuration", "kubevirt-worker-tuning"],
        "tuning_config": None,
    }


async def test_the_draft_lists_its_choices_and_says_why_it_cannot_be_created(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    query = {"mastertag": "4.99.1", "zone": "az2", "infra_env": "c200-mtl-az1"}
    draft = (await client.get(DRAFT, params=query, headers=auth(support.ALICE))).json()
    assert draft["yaml"] is None
    assert draft["zones"] == ["az1"]
    assert draft["problems"] == [
        "zone 'az2' is not one of: az1",
        "MCE ocp4-prod-seed-site1-az1-a can host 4.18.56, 4.17.58, 4.16.55; "
        "4.99.1 is not one of them",
    ]
    chosen = {"mastertag": "4.17.58", "workers": 7}
    draft = (await client.get(DRAFT, params=chosen, headers=auth(support.ALICE))).json()
    assert draft["problems"] == []
    assert "mastertag: 4.17.58\n" in draft["yaml"] and "replicas: 7\n" in draft["yaml"]
    too_many = await client.get(DRAFT, params={"workers": 41}, headers=auth(support.ALICE))
    assert too_many.status_code == 422


async def test_a_live_hub_gives_the_zones_pools_and_several_are_a_choice(
    auth: Auth, support: Any, gitlab: InMemoryGitLab, clock: Any
) -> None:
    pools = ["c200-mtl-az1", "r760-mtl-az1", "r760-mtl-az2", "c200-kv32-az1", "legacy-pool"]
    hub = FakeHubApi(infra_envs={SEED: {"inventory": pools}})
    async with client_with(support, gitlab, clock, hub=hub) as client:
        draft = (await client.get(DRAFT, headers=auth(support.ALICE))).json()
        assert (draft["infra_envs_from"], draft["infra_envs"]) == (
            "hub",
            ["c200-mtl-az1", "r760-mtl-az1"],  # bare metal in az1 only
        )
        assert draft["infra_env"] is None
        assert draft["problems"] == ["choose the InfraEnv: c200-mtl-az1, r760-mtl-az1"]
        params = {"infra_env": "c200-mtl-az1"}
        chosen = (await client.get(DRAFT, params=params, headers=auth(support.ALICE))).json()
        assert "- infraEnvName: c200-mtl-az1\n" in chosen["yaml"]
        unreachable = FakeHubApi(unavailable=[SEED])
    async with client_with(support, gitlab, clock, hub=unreachable) as client:
        failed = await client.get(DRAFT, headers=auth(support.ALICE))
        assert failed.status_code == 502  # a hub that does not answer is never read around


async def test_with_no_kv_cluster_to_copy_the_owner_is_asked_for(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    pid = await support.project_id(gitlab, support.DAY1)
    removed = [FileChange.delete(RepoPath(path)) for path in KV_FILES]
    await gitlab.commit(pid, branch="main", message="no KV cluster", changes=removed)
    draft = (await client.get(DRAFT, headers=auth(support.ALICE))).json()
    assert (draft["name"], draft["model"]) == ("ocp4-prod-kv-site1-az1-a", None)
    assert draft["problems"] == [
        "seed ocp4-prod-seed-site1-az1-a has no bare-metal InfraEnv <flavor>-mtl-az1 (files)",
        "with no KV cluster to copy, owner lacks merkaz, anaf, mador",
    ]


# ── The create ───────────────────────────────────────────────────────────────


async def test_a_create_starts_provision_cluster_on_the_seed_with_the_drafts_file(
    client: httpx.AsyncClient, auth: Auth, support: Any, provision: FakeProvisionWorkflow
) -> None:
    body = {"name": NEXT, "zone": "az1", "infra_env": "r760-mtl-az1", "workers": 3}
    created = await client.post(CREATE, json=body, headers=auth(support.ALICE))
    assert created.status_code == 202, created.text
    assert created.json()["workflow_id"] == f"provision-cluster-{NEXT}"
    (started,) = provision.starts
    assert started == {"cluster": "prod-kv-site1-az1-c", "mce": SEED, "content": EXPECTED}
    run = await client.get(f"/api/day1/clusters/{NEXT}/provision-run", headers=auth(support.ALICE))
    assert (run.status_code, run.json()["cluster"]) == (200, NEXT)


async def test_a_name_another_create_took_since_the_draft_is_a_conflict(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.open_provision_mr(gitlab, NEXT, mce=SEED)
    draft = (await client.get(DRAFT, headers=auth(support.ALICE))).json()
    assert draft["name"] == "ocp4-prod-kv-site1-az1-d"  # an open create holds -c
    stale = await client.post(CREATE, json={"name": NEXT}, headers=auth(support.ALICE))
    assert (stale.status_code, stale.json()["code"]) == (409, "REVISION_CONFLICT")
    assert "ocp4-prod-kv-site1-az1-d" in stale.json()["detail"]


async def test_a_refused_create_and_the_orchestrators_words_reach_the_dialog(
    client: httpx.AsyncClient, auth: Auth, support: Any, provision: FakeProvisionWorkflow
) -> None:
    refused = await client.post(
        CREATE, json={"name": NEXT, "mastertag": "4.99.1"}, headers=auth(support.ALICE)
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "VALIDATION_ERROR")
    assert "4.99.1 is not one of them" in refused.json()["details"]["problems"][0]
    assert provision.starts == []
    provision.fail_start = ProvisionRefusedError(
        "the orchestrator refused to provision prod-kv-site1-az1-c", ["mce: no such folder"]
    )
    words = await client.post(CREATE, json={"name": NEXT}, headers=auth(support.ALICE))
    assert words.json()["details"]["problems"] == ["mce: no such folder"]


async def test_the_template_must_write_the_kv_clusters_zone(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    template = (await gitlab.read_file(await support.project_id(gitlab, support.SPECS), RepoPath(
        "cluster-template.j2"), ref="main")).content  # fmt: skip
    older = template.replace("{% if np.node_labels", "{% if false and np.node_labels")
    await support.push(
        gitlab, support.SPECS, branch="main", file="cluster-template.j2", content=older
    )
    draft = (await client.get(DRAFT, headers=auth(support.ALICE))).json()
    assert draft["yaml"] is None
    assert "does not write the KV cluster's zone" in draft["problems"][0]


# ── Who may ──────────────────────────────────────────────────────────────────


async def test_a_viewer_is_refused_before_anything_is_read_for_any_name(
    client: httpx.AsyncClient, auth: Auth, support: Any, provision: FakeProvisionWorkflow
) -> None:
    viewer = auth(support.VIEWER)
    for seed in (SEED, "ocp4-prod-mce-site1-a", "ocp4-prod-seed-nowhere-az1-a"):
        draft = await client.get(f"/api/day1/seeds/{seed}/kv-cluster-draft", headers=viewer)
        create = await client.post(
            f"/api/day1/seeds/{seed}/kv-clusters", json={"name": NEXT}, headers=viewer
        )
        assert (draft.status_code, create.status_code) == (403, 403), seed
        # The same answer for every name: it says nothing of which folders are seeds
        assert draft.json()["detail"] == create.json()["detail"] == "This needs the admin role."
    assert provision.starts == []


async def test_a_customer_mce_or_a_missing_folder_is_no_seed(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    for folder in ("ocp4-prod-mce-site1-a", "ocp4-prod-seed-nowhere-az1-a"):
        missing = await client.get(
            f"/api/day1/seeds/{folder}/kv-cluster-draft", headers=auth(support.ALICE)
        )
        assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND"), folder


async def test_a_seed_whose_name_gives_no_zone_takes_it_from_its_infra_envs(
    auth: Auth, support: Any, gitlab: InMemoryGitLab, clock: Any
) -> None:
    hub_shaped = "ocp4-prod-mce-seed-site1-a"  # ADR-0067's amendment: a seed, with no zone
    rules = 'mce:\n  version: 2.8.2\n  supportedHostedVersions: ["4.18"]\n'
    rules_file = f"upgrade/mces/{hub_shaped}.yaml"
    await support.push(gitlab, support.DAY1, branch="main", file=rules_file, content=rules)
    values = f"sites/site1/mces/{hub_shaped}/values.yaml"
    await support.push(
        gitlab, support.DAY1, branch="main", file=values, content="mastertag: 4.18.56\n"
    )
    hub = FakeHubApi(infra_envs={hub_shaped: {"inventory": ["r760-mtl-az1", "r760-mtl-az2"]}})
    draft_url = f"/api/day1/seeds/{hub_shaped}/kv-cluster-draft"
    async with client_with(support, gitlab, clock, hub=hub) as client:
        draft = (await client.get(draft_url, headers=auth(support.ALICE))).json()
        assert (draft["zones"], draft["zone"], draft["name"]) == (["az1", "az2"], None, None)
        assert draft["problems"] == ["choose the zone: az1, az2"]
        params = {"zone": "az2"}
        chosen = (await client.get(draft_url, params=params, headers=auth(support.ALICE))).json()
        assert chosen["name"] == "ocp4-prod-kv-site1-az2-a"
        assert chosen["infra_env"] == "r760-mtl-az2"
        assert chosen["problems"] == []
        assert 'nodeLabels: {"topology.kubernetes.io/zone": "az2"}' in chosen["yaml"]
