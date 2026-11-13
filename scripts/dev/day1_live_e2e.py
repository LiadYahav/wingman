"""Run the day1 service against a real (local) GitLab and walk a cluster's whole life.

    uv run python scripts/dev/day1_live_e2e.py --token <local token> \
        [--sandbox-chart <dir>] [--production-chart <dir>] [--keep]

1. Creates fresh copies of ``gitops-day1/platform-config`` and
   ``wingman/cluster-specs`` (from dev/gitlab-fixtures) in the group
   ``wingman-day1-e2e``, so the shared seeded projects are never touched.
2. Starts ``uvicorn wingman_day1.main:app`` on them (``WINGMAN_GIT_BACKEND=gitlab``,
   dev login), and over HTTP: lists sites, MCEs and clusters; creates a
   cluster from ``agent-standard``; pushes the allocate-segment workflow's
   ``vlanId``/``dhcp_values`` onto the MR branch as a bot would; checks that
   approving the stale commit is refused; approves the new head as a second
   user; edits the merged file; approves the edit; opens the delete MR and
   approves it.
   Then flavors v2 (ADR-0037): imports two hand-written clusters into
   ``agent-baseline`` (only the header changes), syncs one after another file
   moved (GitLab takes the older commit as the guard), and checks a sync of a
   file that moved after its preview is refused.
3. With a chart dir, renders the cluster file as the hcAppset does
   (``helm template`` with the four value layers and ``clusterName``/``site``/
   ``mce``) and checks a HostedCluster and NodePools come out.
4. Deletes the projects it created, unless ``--keep``.

Refuses any GitLab that is not local (like seed_gitlab.py).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
import yaml

from wingman_core.testing.fixtures import default_fixture_root, load_fixture_projects

LOCAL_HOSTS = {"localhost", "127.0.0.1"}
GROUP = "wingman-day1-e2e"
SITE, MCE = "site1", "ocp4-prod-mce-site1-a"
CLUSTER = "ocp4-prod-falcon-site1"
CLUSTER_PATH = f"sites/{SITE}/mces/{MCE}/hostedClusters/{CLUSTER}.yaml"
# Throwaway secrets for the day1 process this script starts and stops.
DEV_SECRET = "e2e-dev-login-secret-0123456789abcdef"  # noqa: S105
JWT_SECRET = "e2e-jwt-secret-0123456789abcdef-0123456789"  # noqa: S105


def step(text: str) -> None:
    """Print the heading of the next step."""
    print(f"\n== {text}", flush=True)


def check(condition: object, text: str) -> None:
    """Stop the run with ``text`` unless ``condition`` holds."""
    if not condition:
        raise SystemExit(f"FAILED: {text}")
    print(f"   ok  {text}", flush=True)


async def make_projects(admin: httpx.AsyncClient, suffix: str) -> dict[str, str]:
    """Create fresh day1 and specs projects from the fixtures; return their paths by role."""
    group = await admin.get(f"/groups/{GROUP}")
    if group.status_code == 404:
        group = await admin.post(
            "/groups", json={"name": GROUP, "path": GROUP, "visibility": "private"}
        )
    group.raise_for_status()
    namespace_id = group.json()["id"]
    wanted = {"gitops-day1/platform-config": "day1", "wingman/cluster-specs": "specs"}
    paths: dict[str, str] = {}
    for fixture in load_fixture_projects(default_fixture_root()):
        if fixture.path_with_namespace not in wanted:
            continue
        name = f"{fixture.path_with_namespace.split('/')[1]}-{suffix}"
        created = await admin.post(
            "/projects",
            json={
                "name": name,
                "path": name,
                "namespace_id": namespace_id,
                "default_branch": "main",
            },
        )
        created.raise_for_status()
        actions = [
            {"action": "create", "file_path": p, "content": c}
            for p, c in sorted(fixture.files.items())
        ]
        commit = await admin.post(
            f"/projects/{created.json()['id']}/repository/commits",
            json={
                "branch": "main",
                "commit_message": "Seed from dev/gitlab-fixtures",
                "actions": actions,
            },
        )
        commit.raise_for_status()
        paths[wanted[fixture.path_with_namespace]] = f"{GROUP}/{name}"
        print(f"   created {GROUP}/{name}")
    return paths


async def delete_projects(admin: httpx.AsyncClient, paths: dict[str, str]) -> None:
    """Delete the projects ``make_projects`` created."""
    for path in paths.values():
        response = await admin.delete(f"/projects/{quote(path, safe='')}")
        print(f"   delete {path}: {response.status_code}")


def free_port() -> int:
    """A local port nothing listens on."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def start_service(
    url: str, token: str, paths: dict[str, str], port: int
) -> subprocess.Popen[bytes]:
    """Start day1 on ``port`` against the given projects, with dev login."""
    env = {
        **os.environ,
        "WINGMAN_ENVIRONMENT": "development",
        "WINGMAN_GIT_BACKEND": "gitlab",
        "GITLAB_URL": url,
        "GITLAB_TOKEN": token,
        "JWT_SECRET_KEY": JWT_SECRET,
        "WINGMAN_ADMIN_GROUPS": "wingman-dev-admins",
        "WINGMAN_VIEWER_GROUPS": "wingman-dev-viewers",
        "DAY1_GITLAB_PROJECT_ID": paths["day1"],
        "SPECS_GITLAB_PROJECT_ID": paths["specs"],
        "DEV_AUTH_ENABLED": "true",
        "DEV_AUTH_SECRET": DEV_SECRET,
        "DAY2_SERVICE_URL": "http://127.0.0.1:9",
    }
    return subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [
            sys.executable,
            "-m",
            "uvicorn",
            "wingman_day1.main:app",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
    )


async def wait_ready(api: httpx.AsyncClient) -> None:
    """Wait up to 30 s for day1's readiness probe."""
    for _ in range(60):
        try:
            if (await api.get("/health/ready")).status_code == 200:
                return
        except httpx.TransportError:
            pass
        await asyncio.sleep(0.5)
    raise SystemExit("day1 did not become ready")


async def login(api: httpx.AsyncClient, username: str) -> dict[str, str]:
    """Dev-login ``username`` as an admin; return the auth header."""
    response = await api.post(
        "/api/auth/dev-login", json={"username": username, "role": "admin", "secret": DEV_SECRET}
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def approve(api: httpx.AsyncClient, iid: int, approver: dict[str, str]) -> dict[str, object]:
    """Approve MR ``iid`` at the sha its detail shows, and check it merged."""
    detail = (await api.get(f"/api/day1/approvals/{iid}", headers=approver)).json()
    merged = await api.post(
        f"/api/day1/approvals/{iid}/approve", json={"sha": detail["mr"]["sha"]}, headers=approver
    )
    check(
        merged.status_code == 200,
        f"!{iid} approved and merged ({merged.status_code} {merged.text[:200]})",
    )
    return merged.json()


async def flow(api: httpx.AsyncClient, admin: httpx.AsyncClient, paths: dict[str, str]) -> str:  # noqa: PLR0915 - baseline: a scripted walk, step by step
    """Walk the cluster's life (module docstring, step 2); return the merged cluster file."""
    alice, bob = await login(api, "alice"), await login(api, "bob")

    step("read the repo")
    sites = (await api.get("/api/day1/sites", headers=alice)).json()
    check(sites == ["site1", "site2"], f"sites {sites}")
    mces = (await api.get("/api/day1/mces", headers=alice)).json()
    prod = next(m for m in mces if m["name"] == MCE)
    check(
        prod["default_mastertag"] == "4.16.27-x86_64",
        f"{MCE} default mastertag {prod['default_mastertag']}",
    )
    check(prod["hub_version"] == "4.16.27-x86_64", f"{MCE} hub version {prod['hub_version']}")
    offered = (await api.get(f"/api/day1/mces/{MCE}/openshift-versions", headers=alice)).json()
    check(
        offered["versions"] == ["4.18.56", "4.17.58", "4.16.55"] and not offered["problems"],
        f"{MCE} offers {offered}",
    )
    clusters = (await api.get("/api/day1/clusters", headers=alice)).json()
    flagged = [c["name"] for c in clusters if not c["naming"]["follows_convention"]]
    check(len(clusters) == 14, f"{len(clusters)} clusters listed; off-convention: {flagged}")

    step("create from agent-standard")
    body = {
        "name": CLUSTER,
        "site": SITE,
        "mce": MCE,
        "spec_name": "agent-standard",
        "spec_version": "1.0.0",
        "variables": {
            "owner_merkaz": "1234",
            "owner_anaf": "56",
            "owner_mador": "7",
            "openshift_release_version": "4.18.56-x86_64",
            "nodepools": [
                {
                    "infra_env": "dell-r660-site1-128c-1024gb-5tb",
                    "replicas": 2,
                    "configs": [{"name": "worker-kubeletconfig-reserved"}],
                },
                {
                    "infra_env": "hp-gen11-site1-64c",
                    "replicas": 1,
                    "configs": [{"name": "nic-ring-buffer"}],
                },
            ],
        },
        "addon_overrides": {"redbull/cluster-roles": {"extraRoles": ["viewer"]}},
    }
    created = await api.post("/api/day1/clusters", json=body, headers=alice)
    check(
        created.status_code == 201, f"create MR opened ({created.status_code} {created.text[:200]})"
    )
    mr = created.json()
    print(f"   {mr['title']}  branch={mr['source_branch']}  labels={mr['labels']}")
    pending = (await api.get("/api/day1/approvals", headers=alice)).json()
    check([p["iid"] for p in pending] == [mr["iid"]], "the new MR is pending at once")

    step("the allocate-segment workflow commits onto the MR branch")
    project = quote(paths["day1"], safe="")
    file_url = f"/projects/{project}/repository/files/{quote(CLUSTER_PATH, safe='')}"
    raw = await admin.get(file_url, params={"ref": mr["source_branch"]})
    raw.raise_for_status()
    content = base64.b64decode(raw.json()["content"]).decode()
    allocated = content + 'vlanId: 412\ndhcp_values:\n  network: "10.20.99.0"\n'
    pushed = await admin.put(
        file_url,
        json={
            "branch": mr["source_branch"],
            "content": allocated,
            "commit_message": "allocate-segment: vlanId 412 [skip ci]",
            "author_name": "allocate-segment",
            "author_email": "workflow@example.invalid",
        },
    )
    pushed.raise_for_status()
    stale = await api.post(
        f"/api/day1/approvals/{mr['iid']}/approve", json={"sha": mr["sha"]}, headers=bob
    )
    check(
        stale.status_code == 409,
        f"approving the reviewed-but-stale head is refused ({stale.status_code})",
    )
    own = await api.get(f"/api/day1/approvals/{mr['iid']}", headers=alice)
    refused = await api.post(
        f"/api/day1/approvals/{mr['iid']}/approve",
        json={"sha": own.json()["mr"]["sha"]},
        headers=alice,
    )
    check(
        refused.status_code == 403, f"the requester cannot approve ({refused.json().get('code')})"
    )
    await approve(api, mr["iid"], bob)

    step("the merged cluster")
    await asyncio.sleep(1)
    detail = (await api.get(f"/api/day1/clusters/{CLUSTER}", headers=alice)).json()
    check(
        detail["values"]["network"]["vlan_id"] == 412,
        f"VLAN from the file: {detail['values']['network']}",
    )
    check(
        detail["metadata"]["requested_addons"][0]["override_values"] == {"extraRoles": ["viewer"]},
        "addon overrides kept",
    )
    check(
        detail["hosted_cluster"]["name"] == "ocp4-prod-falcon-site1",
        f"HostedCluster {detail['hosted_cluster']}",
    )
    history = (await api.get(f"/api/day1/clusters/{CLUSTER}/history", headers=alice)).json()
    print("   history:", [(c["short_sha"], c["author"], c["message"][:40]) for c in history])

    step("edit")
    edited_yaml = detail["yaml"].replace("replicas: 1", "replicas: 3")
    edited = await api.patch(
        f"/api/day1/clusters/{CLUSTER}",
        json={
            "updated_yaml": edited_yaml,
            "change_summary": "Scale hp pool to 3",
            "last_commit_id": detail["last_commit_id"],
        },
        headers=alice,
    )
    check(edited.status_code == 200, f"modify MR opened ({edited.status_code} {edited.text[:200]})")
    await approve(api, edited.json()["iid"], bob)
    await asyncio.sleep(1)
    final = (await api.get(f"/api/day1/clusters/{CLUSTER}", headers=alice)).json()
    check(final["values"]["nodepools"][1]["replicas"] == 3, "the edit is on main")

    step("delete")
    deleted = await api.delete(
        f"/api/day1/clusters/{CLUSTER}",
        params={"last_commit_id": final["last_commit_id"]},
        headers=alice,
    )
    check(deleted.status_code == 200, f"delete MR opened: {deleted.json().get('title')}")
    await approve(api, deleted.json()["iid"], bob)
    await asyncio.sleep(1)
    gone = await api.get(f"/api/day1/clusters/{CLUSTER}", headers=alice)
    check(
        gone.status_code == 404, f"the cluster is gone after the delete merges ({gone.status_code})"
    )
    audit = (await api.get("/api/day1/audit/merge-requests", headers=alice)).json()
    print(
        "   audit:", [(m["repo"], m["iid"], m["state"], m["author"]["username"]) for m in audit[:4]]
    )
    return final["yaml"]


HOSTED = f"sites/{SITE}/mces/{MCE}/hostedClusters"
LARK, HERON, HERZI = "ocp4-prod-lark-site1", "ocp4-prod-heron-site1", "ocp4-prod-herzi-site1"
FLAVOR = "agent-baseline"
CI_MARKER = "# === Added by CI ==="


async def read_main(admin: httpx.AsyncClient, project: str, path: str) -> str:
    """A file's text on main, read straight from GitLab."""
    raw = await admin.get(
        f"/projects/{quote(project, safe='')}/repository/files/{quote(path, safe='')}/raw",
        params={"ref": "main"},
    )
    raw.raise_for_status()
    return raw.text


async def push_main(admin: httpx.AsyncClient, project: str, path: str, content: str) -> None:
    """Commit ``content`` to ``path`` on main as a person would, outside Wingman."""
    pushed = await admin.put(
        f"/projects/{quote(project, safe='')}/repository/files/{quote(path, safe='')}",
        json={"branch": "main", "content": content, "commit_message": f"edit {path} by hand"},
    )
    pushed.raise_for_status()


async def flavor_flow(  # noqa: PLR0915 - baseline: a scripted walk, step by step
    api: httpx.AsyncClient, admin: httpx.AsyncClient, paths: dict[str, str]
) -> None:
    """Import two hand-written clusters into a flavor, then sync one (ADR-0037)."""
    alice, bob = await login(api, "alice"), await login(api, "bob")
    day1 = paths["day1"]
    lark_path, heron_path = f"{HOSTED}/{LARK}.yaml", f"{HOSTED}/{HERON}.yaml"
    lark_before = await read_main(admin, day1, lark_path)
    heron_before = await read_main(admin, day1, heron_path)

    step(f"import {LARK} and {HERON} into {FLAVOR}")
    preview = await api.post(
        f"/api/day1/specs/{FLAVOR}/import/preview",
        json={"clusters": [{"name": LARK}, {"name": HERON}]},
        headers=alice,
    )
    check(
        preview.status_code == 200, f"import preview ({preview.status_code} {preview.text[:200]})"
    )
    shown = preview.json()
    check(
        [c["status"] for c in shown["clusters"]] == ["ready", "ready"],
        "both are ready to join the flavor",
    )
    imported = await api.post(
        f"/api/day1/specs/{FLAVOR}/import",
        json={
            "spec_version": shown["spec_version"],
            "clusters": [
                {k: c[k] for k in ("name", "site", "mce", "last_commit_id")}
                for c in shown["clusters"]
            ],
        },
        headers=alice,
    )
    check(imported.status_code == 201, f"import MRs opened ({imported.status_code})")
    result = imported.json()
    check(
        [m["name"] for m in result["merge_requests"]] == [LARK, HERON] and result["failed"] == [],
        "one import MR per cluster (ADR-0044)",
    )
    for opened in result["merge_requests"]:
        print(f"   {opened['merge_request']['title']}")
        await approve(api, opened["merge_request"]["iid"], bob)
    await asyncio.sleep(1)
    header = f'# specName: "{FLAVOR}"\n# specVersion: "1.0.0"\n'
    check(
        await read_main(admin, day1, lark_path) == header + lark_before
        and await read_main(admin, day1, heron_path) == header + heron_before,
        "the import wrote only the header: every other byte of both files is as it was",
    )
    drift = (await api.get(f"/api/day1/clusters/{LARK}/drift", headers=alice)).json()
    check(
        [d["file_key"] for d in drift["value_drift"]]
        == ["nodepool[0].configs", "nodepool[1].configs"],
        f"{LARK} drifts on both nodepools' configs (state {drift['state']})",
    )

    step(f"sync {LARK}, after someone else changed another file")
    sync = await api.post(f"/api/day1/clusters/{LARK}/sync/preview", json={}, headers=alice)
    check(sync.status_code == 200, f"sync preview ({sync.status_code} {sync.text[:200]})")
    plan = sync.json()
    check(plan["can_sync"] and len(plan["removals"]) == 2, f"removals {plan['removals']}")
    herzi_path = f"{HOSTED}/{HERZI}.yaml"
    await push_main(admin, day1, herzi_path, await read_main(admin, day1, herzi_path) + "# x\n")
    body: dict[str, object] = {
        "last_commit_id": plan["last_commit_id"],
        "spec_version": plan["spec_version"],
    }
    unconfirmed = await api.post(f"/api/day1/clusters/{LARK}/sync", json=body, headers=alice)
    check(unconfirmed.status_code == 422, "a sync that does not confirm its removals is refused")
    body["confirm_removals"] = [
        {"nodepool": r["nodepool"]["index"], "name": r["name"]} for r in plan["removals"]
    ]
    synced = await api.post(f"/api/day1/clusters/{LARK}/sync", json=body, headers=alice)
    check(
        synced.status_code == 201,
        f"GitLab takes the preview's older commit as the guard ({synced.status_code} "
        f"{synced.text[:200]})",
    )
    print(f"   {synced.json()['title']}")
    await approve(api, synced.json()["iid"], bob)
    await asyncio.sleep(1)
    after = await read_main(admin, day1, lark_path)
    check(
        after.split(CI_MARKER)[1] == lark_before.split(CI_MARKER)[1]
        and "vlanId: 1412" in after
        and "restored-example-config  #" not in after,
        "the sync changed the configs and left vlanId and the CI block as they were",
    )
    detail = (await api.get(f"/api/day1/clusters/{LARK}", headers=alice)).json()
    check(
        [p["configs"] for p in detail["values"]["nodepools"]]
        == [
            ["nm-conf-prod-lark-site1-dell", "nic-ring-buffer", "workers-chrony-configuration"],
            [
                "nm-conf-prod-lark-site1-dell-data",
                "workers-chrony-configuration",
                "nic-ring-buffer",
            ],
        ],
        "each nodepool now holds exactly the flavor's configs",
    )
    drift = (await api.get(f"/api/day1/clusters/{LARK}/drift", headers=alice)).json()
    check(drift["value_drift"] == [], f"no locked value differs now (state {drift['state']})")

    step(f"a sync of {HERON} whose file moved after the preview")
    hardware = {
        "hardware": [{"nodepool": 0, "hardware": "dell"}, {"nodepool": 1, "hardware": "dell"}]
    }
    heron = await api.post(f"/api/day1/clusters/{HERON}/sync/preview", json=hardware, headers=alice)
    check(
        heron.status_code == 200 and heron.json()["can_sync"], "heron syncs once hardware is chosen"
    )
    plan = heron.json()
    await push_main(admin, day1, heron_path, await read_main(admin, day1, heron_path) + "# y\n")
    moved = await api.post(
        f"/api/day1/clusters/{HERON}/sync",
        json={
            **hardware,
            "last_commit_id": plan["last_commit_id"],
            "spec_version": plan["spec_version"],
            "confirm_removals": [
                {"nodepool": r["nodepool"]["index"], "name": r["name"]} for r in plan["removals"]
            ],
        },
        headers=alice,
    )
    check(
        moved.status_code == 409 and moved.json()["code"] == "REVISION_CONFLICT",
        f"the moved file is refused ({moved.status_code})",
    )


def helm_render(
    chart: Path,
    cluster_yaml: str,
    *,
    strip: bool,
    extra: list[str],
    values_root: Path | None = None,
) -> dict[str, int]:
    """``helm template`` with the hcAppset's layers; a missing layer is skipped, as there."""
    root = values_root or default_fixture_root() / "gitops-day1" / "platform-config"
    layers = [
        root / "sites/configValues.yaml",
        root / f"sites/{SITE}/values.yaml",
        root / f"sites/{SITE}/mces/{MCE}/values.yaml",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        cluster_file = Path(tmp) / f"{CLUSTER}.yaml"
        cluster_file.write_text(cluster_yaml, encoding="utf-8")
        cluster_name = CLUSTER.removeprefix("ocp4-") if strip else CLUSTER
        argv = [
            "helm",
            "template",
            CLUSTER,
            str(chart),
            *(arg for layer in layers if layer.exists() for arg in ("-f", str(layer))),
            "-f",
            str(cluster_file),
            "--set-string",
            f"clusterName={cluster_name},site={SITE},mce={MCE}",
            *extra,
        ]
        result = subprocess.run(argv, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise SystemExit(f"helm template failed:\n{result.stderr}")
    kinds: dict[str, int] = {}
    for doc in yaml.safe_load_all(result.stdout):
        if isinstance(doc, dict):
            kinds[doc.get("kind", "?")] = kinds.get(doc.get("kind", "?"), 0) + 1
            if doc.get("kind") == "HostedCluster":
                print(
                    f"   HostedCluster {doc['metadata']['name']} in {doc['metadata']['namespace']}"
                )
            if doc.get("kind") == "NodePool":
                print(
                    f"   NodePool {doc['metadata']['name']} replicas={doc['spec'].get('replicas')}"
                )
    return kinds


async def main() -> int:
    """Parse the arguments, run the flow and the renders, clean up."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default=os.environ.get("GITLAB_URL", "http://localhost:8929"))
    parser.add_argument("--token", default=os.environ.get("GITLAB_TOKEN", ""))
    parser.add_argument(
        "--sandbox-chart",
        type=Path,
        action="append",
        default=[],
        help="GitHub-sandbox hostedclusters-setup chart dir to render with",
    )
    parser.add_argument(
        "--production-chart",
        type=Path,
        action="append",
        default=[],
        help="production (GitLab) hostedclusters-setup chart dir to render with",
    )
    parser.add_argument(
        "--production-values",
        type=Path,
        default=None,
        help="a platform-config checkout whose sites/ layers the production chart "
        "needs (its globals: etcd, images); defaults to the fixtures",
    )
    parser.add_argument("--keep", action="store_true", help="keep the projects it created")
    args = parser.parse_args()
    if not args.token:
        parser.error("no token: pass --token or set GITLAB_TOKEN")
    if urlparse(args.url).hostname not in LOCAL_HOSTS:
        parser.error(f"{args.url} is not a local GitLab")

    suffix = uuid.uuid4().hex[:8]
    port = free_port()
    async with httpx.AsyncClient(
        base_url=f"{args.url.rstrip('/')}/api/v4", headers={"PRIVATE-TOKEN": args.token}, timeout=60
    ) as admin:
        step(f"fresh projects in {GROUP}")
        paths = await make_projects(admin, suffix)
        service = start_service(args.url, args.token, paths, port)
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=60) as api:
                await wait_ready(api)
                final_yaml = await flow(api, admin, paths)
                await flavor_flow(api, admin, paths)
        finally:
            service.terminate()
            service.wait(timeout=10)
            if not args.keep:
                step("clean up")
                await delete_projects(admin, paths)
    print(f"\nflow finished in {time.monotonic() - started:.1f}s")
    print("\nfinal cluster file (as merged, before the delete):\n" + final_yaml)

    charts = [(c, True) for c in args.sandbox_chart] + [(c, False) for c in args.production_chart]
    if charts and not shutil.which("helm"):
        raise SystemExit("helm is not on PATH")
    for chart, sandbox in charts:
        # The sandbox hcAppset passes the full stem as clusterName, and that chart renders the
        # HostedCluster only with hostedCluster.enabled (the lab MCE sets it in its values.yaml;
        # the prod-shaped MCE used here does not). Production strips ocp4- and always renders.
        mode = "sandbox: full stem" if sandbox else "production: ocp4- stripped"
        step(f"helm template {chart.name} ({mode})")
        extra = ["--set", "hostedCluster.enabled=true"] if sandbox else []
        values_root = None if sandbox else args.production_values
        kinds = helm_render(
            chart, final_yaml, strip=not sandbox, extra=extra, values_root=values_root
        )
        print(f"   kinds: {kinds}")
        check(kinds.get("HostedCluster") == 1, "one HostedCluster rendered")
        check(kinds.get("NodePool") == 2, "two NodePools rendered")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
