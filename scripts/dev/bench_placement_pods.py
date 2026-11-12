"""What counting an MCE's pods per node costs, as Table rows or as pod objects (ADR-0050).

Placement's free pods need, for every pod that is not Succeeded or Failed,
only the node it is bound to. The API server can send that two ways:

- ``objects``: the PodList (``Accept: application/json``), every pod object
  whole; a pod is kilobytes (its spec, its status and its managedFields);
- ``table``: the same list as a ``meta.k8s.io/v1`` Table with
  ``includeObject=None``, one row of nine short cells per pod. This is what
  ``HttpHubApi.pods_per_node`` asks for.

Both are served a page of 500 at a time through ``httpx.MockTransport``; the
``table`` case runs the real adapter, the ``objects`` case the same pages
parsed with ``json`` and counted by ``spec.nodeName``. The pod object is
synthetic but shaped like a hosted control plane's pod on an MCE (several
containers, probes, env, volumes, managedFields); real ones are often
larger. Nothing here talks to a network.

    uv run python scripts/dev/bench_placement_pods.py --pods 3000 --nodes 12
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import time
from collections import Counter
from typing import Any

import httpx

from wingman_day1.infrastructure.hub_api import PAGE_SIZE, HttpHubApi

MCE = "ocp4-prod-mce-site1-a"


def container(name: str, i: int) -> dict[str, Any]:
    """One container of a control-plane pod, as the API server returns it."""
    return {
        "name": name,
        "image": f"quay.io/openshift-release-dev/ocp-v4.0-art-dev@sha256:{i:064x}",
        "command": ["/usr/bin/hypershift-component", f"--component={name}"],
        "args": [f"--config=/etc/{name}/config.yaml", "--v=2", "--tls-min-version=VersionTLS12"],
        "env": [{"name": f"ENV_{k}", "value": f"value-{k}-{i}"} for k in range(8)],
        "ports": [{"name": "https", "containerPort": 6443 + i % 7, "protocol": "TCP"}],
        "resources": {"requests": {"cpu": "100m", "memory": "256Mi"}},
        "volumeMounts": [
            {"name": f"vol-{k}", "mountPath": f"/etc/{name}/{k}", "readOnly": True}
            for k in range(6)
        ],
        "livenessProbe": {
            "httpGet": {"path": "/livez", "port": 6443, "scheme": "HTTPS"},
            "initialDelaySeconds": 45,
            "timeoutSeconds": 10,
            "periodSeconds": 10,
            "successThreshold": 1,
            "failureThreshold": 3,
        },
        "readinessProbe": {
            "httpGet": {"path": "/readyz", "port": 6443, "scheme": "HTTPS"},
            "timeoutSeconds": 10,
            "periodSeconds": 10,
            "successThreshold": 1,
            "failureThreshold": 3,
        },
        "terminationMessagePath": "/dev/termination-log",
        "terminationMessagePolicy": "FallbackToLogsOnError",
        "imagePullPolicy": "IfNotPresent",
        "securityContext": {"runAsNonRoot": True, "allowPrivilegeEscalation": False},
    }


def pod(i: int, node: str) -> dict[str, Any]:
    """A synthetic hosted-control-plane pod object."""
    names = ("kube-apiserver", "audit-logs", "konnectivity", "bootstrap")
    containers = [container(name, i) for name in names[: 2 + i % 3]]
    return {
        "metadata": {
            "name": f"kube-apiserver-{i:05d}-7d9f8b6c5d-x2k4p",
            "namespace": f"hcp-prod-cluster-{i // 70:03d}-ocp4-prod-cluster-{i // 70:03d}",
            "uid": f"{i:08x}-0000-4000-8000-000000000000",
            "resourceVersion": str(1_000_000 + i),
            "creationTimestamp": "2026-10-01T08:00:00Z",
            "labels": {"app": "kube-apiserver", "hypershift.openshift.io/control-plane": "true"},
            "annotations": {"hypershift.openshift.io/release-image": "quay.io/x@sha256:0"},
            "ownerReferences": [
                {"apiVersion": "apps/v1", "kind": "ReplicaSet", "name": "kube-apiserver-7d9f8b6c5d"}
            ],
            "managedFields": [
                {
                    "manager": manager,
                    "operation": "Update",
                    "apiVersion": "v1",
                    "time": "2026-10-01T08:00:00Z",
                    "fieldsType": "FieldsV1",
                    "fieldsV1": {
                        "f:metadata": {"f:labels": {f"f:k{k}": {} for k in range(10)}},
                        "f:spec": {"f:containers": {f'k:{{"name":"c{k}"}}': {} for k in range(4)}},
                    },
                }
                for manager in ("kube-controller-manager", "kubelet")
            ],
        },
        "spec": {
            "containers": containers,
            "volumes": [{"name": f"vol-{k}", "secret": {"secretName": f"s-{k}"}} for k in range(6)],
            "nodeName": node,
            "priorityClassName": "hypershift-api-critical",
            "serviceAccountName": "kube-apiserver",
            "tolerations": [{"key": "hypershift.openshift.io/control-plane", "operator": "Exists"}],
        },
        "status": {
            "phase": "Running",
            "hostIP": "192.0.2.10",
            "podIP": "10.128.4.20",
            "conditions": [
                {"type": kind, "status": "True", "lastTransitionTime": "2026-10-01T08:01:00Z"}
                for kind in ("Initialized", "Ready", "ContainersReady", "PodScheduled")
            ],
            "containerStatuses": [
                {
                    "name": c["name"],
                    "ready": True,
                    "restartCount": 0,
                    "image": c["image"],
                    "imageID": c["image"],
                    "containerID": f"cri-o://{i:064x}",
                    "started": True,
                    "state": {"running": {"startedAt": "2026-10-01T08:00:30Z"}},
                }
                for c in containers
            ],
        },
    }


def table_row(i: int, node: str) -> dict[str, Any]:
    """One Table row of the same pod: nine short cells."""
    cells = [
        f"kube-apiserver-{i:05d}-7d9f8b6c5d-x2k4p",
        "4/4",
        "Running",
        "0",
        "42d",
        "10.128.4.20",
        node,
        "<none>",
        "<none>",
    ]
    return {"cells": cells}


COLUMNS = [
    {"name": n, "type": "string", "format": "", "description": "", "priority": 0}
    for n in (
        "Name",
        "Ready",
        "Status",
        "Restarts",
        "Age",
        "IP",
        "Node",
        "Nominated Node",
        "Readiness Gates",
    )
]


def pages(kind: str, total: int, nodes: int) -> list[bytes]:
    """The response bodies of every page, as the API server would send them."""
    bodies = []
    for start in range(0, total, PAGE_SIZE):
        stop = min(total, start + PAGE_SIZE)
        token = "" if stop == total else f"page-{stop}"
        on = [(i, f"worker-{i % nodes}") for i in range(start, stop)]
        if kind == "table":
            body: dict[str, Any] = {
                "kind": "Table",
                "apiVersion": "meta.k8s.io/v1",
                "metadata": {"continue": token},
                "columnDefinitions": COLUMNS,
                "rows": [table_row(i, n) for i, n in on],
            }
        else:
            body = {
                "kind": "PodList",
                "metadata": {"continue": token},
                "items": [pod(i, n) for i, n in on],
            }
        bodies.append(json.dumps(body, separators=(",", ":")).encode())
    return bodies


async def run_table(bodies: list[bytes]) -> tuple[float, int]:
    """The adapter's own read over the Table pages: seconds, pods counted."""
    replies = iter(bodies)
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, content=next(replies)))
    api = HttpHubApi(tokens={MCE: "t"}, domain="example.invalid", transport=transport)
    start = time.perf_counter()
    counts = await api.pods_per_node(MCE)
    elapsed = time.perf_counter() - start
    await api.aclose()
    return elapsed, sum(counts.values())


def run_objects(bodies: list[bytes]) -> tuple[float, int]:
    """The pod objects parsed and counted by ``spec.nodeName``: seconds, pods counted."""
    start = time.perf_counter()
    counts: Counter[str] = Counter()
    for body in bodies:
        for item in json.loads(body)["items"]:
            counts[item["spec"]["nodeName"]] += 1
    return time.perf_counter() - start, sum(counts.values())


def main() -> None:
    """Print each form's pages, bytes and parse time for the same pods."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--pods", type=int, default=3000)
    parser.add_argument("--nodes", type=int, default=12)
    args = parser.parse_args()
    print(f"{args.pods} pods on {args.nodes} nodes, pages of {PAGE_SIZE}")
    print(f"{'form':8} {'pages':>5} {'bytes':>12} {'gzipped':>10} {'per pod':>8} {'parse s':>8}")
    for kind in ("table", "objects"):
        bodies = pages(kind, args.pods, args.nodes)
        size = sum(len(b) for b in bodies)
        zipped = sum(len(gzip.compress(b)) for b in bodies)
        if kind == "table":
            seconds, counted = asyncio.run(run_table(bodies))
        else:
            seconds, counted = run_objects(bodies)
        if counted != args.pods:
            raise SystemExit(f"{kind}: counted {counted} pods, not {args.pods}")
        print(
            f"{kind:8} {len(bodies):>5} {size:>12,} {zipped:>10,} {size // args.pods:>8,} "
            f"{seconds:>8.3f}"
        )


if __name__ == "__main__":
    main()
