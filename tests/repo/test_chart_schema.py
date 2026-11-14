"""The chart's values schema and its one required value, the image tags (ADR-0059).

Every values file the repository ships renders; a key the chart does not
read, a wrong type, a value outside its enum, range or pattern each fail
``helm template`` and ``helm lint --strict`` with the key named (herzi's
``hack/test-chart.sh``); the keys older releases dropped are accepted and
change nothing; an empty Wingman tag fails naming it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from chart_render import CHART, HELM, TAG, TAGS, render, require_helm, template

require_helm("the chart's schema tests")

SCHEMA = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))
DEFAULT_FIXTURE = CHART / "ci/default-values.yaml"
# Each object a typo is tried in, as a dotted path ("" is the root).
OBJECTS = [
    "",
    *("image", "image.day1", "image.nginx", "gitlab", "day1", "day1.upgrades", "day1.addServers"),
    *("day2", "auth", "devAuth", "route", "openshiftRoute", "openshiftRoute.tls", "ingress", "tls"),
    *("serviceAccount", "resources", "resources.web", "resources.web.limits", "replicaCount"),
    *("clusterStatus", "serverScan", "serverScan.tokenSecret", "workflows", "segmentsManager"),
    *("quickLinks", "monitoring", "monitoring.serviceMonitor", "monitoring.prometheusRule"),
    "monitoring.grafanaDashboard",
]
# (values, the key's path as Helm names it, a word of the reason)
WRONG: list[tuple[dict[str, Any], str, str]] = [
    ({"replicaCount": {"web": "two"}}, "/replicaCount/web", "integer"),
    ({"image": {"day1": {"tag": 3.3}}}, "/image/day1/tag", "string"),
    # a boolean or a non-empty string (wingman.tlsVerify renders both)
    ({"serverScan": {"sslVerify": 0}}, "/serverScan/sslVerify", "want boolean or string"),
    ({"workflows": {"sslVerify": ""}}, "/workflows/sslVerify", "minLength"),
    # tested with `if`: the string "false" is true there
    ({"devAuth": {"enabled": "false"}}, "/devAuth/enabled", "boolean"),
    ({"day1": {"provisioner": "pull-request"}}, "/day1/provisioner", "one of"),
    ({"environment": "staging"}, "/environment", "one of"),
    (
        {"openshiftRoute": {"tls": {"termination": "none"}}},
        "/openshiftRoute/tls/termination",
        "one of",
    ),
    ({"image": {"web": {"pullPolicy": "always"}}}, "/image/web/pullPolicy", "one of"),
    ({"day1": {"cacheTtlSeconds": 90}}, "/day1/cacheTtlSeconds", "maximum"),
    ({"workflows": {"targetsTimeoutSeconds": 121}}, "/workflows/targetsTimeoutSeconds", "maximum"),
    ({"auth": {"jwtExpiryHours": 0}}, "/auth/jwtExpiryHours", "minimum"),
    (
        {"quickLinks": {"sections": [{"name": "Tools", "columns": 7}]}},
        "/quickLinks/sections/0/columns",
        "maximum",
    ),
    ({"gitlab": {"url": "gitlab.internal"}}, "/gitlab/url", "pattern"),
    ({"image": {"nginx": {"digest": "sha256:abc"}}}, "/image/nginx/digest", "pattern"),
    (
        {"auth": {"openshiftApiHost": "https://api.example.com:6443"}},
        "/auth/openshiftApiHost",
        "pattern",
    ),
    (
        {"monitoring": {"serviceMonitor": {"interval": "30 seconds"}}},
        "/monitoring/serviceMonitor/interval",
        "pattern",
    ),
    ({"day1": {"clusterNameStripPrefix": "ocp4"}}, "/day1/clusterNameStripPrefix", "pattern"),
    ({"clusterStatus": {"tokensSecretName": ""}}, "/clusterStatus/tokensSecretName", "minLength"),
]
# What older releases documented and dropped: accepted, ignored.
DEPRECATED_VALUES: dict[str, Any] = {
    "quickLinks": {
        "status": {"enabled": False, "ttlSeconds": 120, "timeoutSeconds": 5, "concurrency": 4},
        "sslVerify": False,
        "argocdTokensSecret": "wingman-argocd-tokens",
    },
    "cache": {"clusterListTtl": 30, "specListTtl": 60, "backgroundRefreshSeconds": 60},
    "paths": {
        "day1ClustersTemplate": "sites/{site}/mces/{mce}/hostedClusters",
        "specsRoot": "specs",
    },
    "gitlab": {"defaultBranch": "main", "sslVerify": "true"},
    "clusterStatus": {"clusterNamePrefix": "ocp4-"},
}
DEPRECATED_PATHS = {
    "quickLinks.status",
    "quickLinks.sslVerify",
    "quickLinks.argocdTokensSecret",
    "cache",
    "paths",
    "gitlab.defaultBranch",
    "gitlab.sslVerify",
    "clusterStatus.clusterNamePrefix",
    "definitions.quickLink.ping",
    "definitions.quickLink.argocd",
}


def nested(path: str, leaf: dict[str, Any]) -> dict[str, Any]:
    """``leaf`` at the dotted ``path``."""
    for key in reversed([part for part in path.split(".") if part]):
        leaf = {key: leaf}
    return leaf


def values_file(tmp_path: Path, values: dict[str, Any]) -> str:
    path = tmp_path / "values.yaml"
    path.write_text(yaml.safe_dump(values), encoding="utf-8")
    return str(path)


def lint(*extra: str) -> subprocess.CompletedProcess[str]:
    assert HELM is not None
    return subprocess.run(  # noqa: S603 - a fixed argv, no shell
        [HELM, "lint", "--strict", str(CHART), "-f", str(DEFAULT_FIXTURE), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def assert_refused(tmp_path: Path, values: dict[str, Any], *words: str) -> None:
    """``helm template`` and ``helm lint --strict`` both refuse ``values``, saying ``words``."""
    file = values_file(tmp_path, values)
    # The tags from the fixture, not --set, which would win over the file's.
    rendered = template("-f", str(DEFAULT_FIXTURE), "-f", file, tags=False)
    for result in (rendered, lint("-f", file)):
        assert result.returncode != 0, (result.args, values)
        said = result.stdout + result.stderr
        for word in words:
            assert word in said, (word, said)


def schema_nodes(node: Any, path: str = "") -> list[tuple[str, dict[str, Any]]]:
    """Every subschema with its dotted path: ``.*`` a map's values, ``[]`` an array's items."""
    if isinstance(node, list):
        return [found for child in node for found in schema_nodes(child, path)]
    if not isinstance(node, dict):
        return []
    found = [(path, node)]
    for name, sub in node.get("definitions", {}).items():
        found += schema_nodes(sub, f"definitions.{name}")
    for name, sub in node.get("properties", {}).items():
        found += schema_nodes(sub, f"{path}.{name}".lstrip("."))
    if isinstance(node.get("additionalProperties"), dict):
        found += schema_nodes(node["additionalProperties"], f"{path}.*")
    found += schema_nodes(node.get("items"), f"{path}[]")
    found += schema_nodes(node.get("allOf"), path)
    return found


@pytest.mark.parametrize(
    "file",
    [
        "values.yaml",
        "values.minikube.yaml",
        *sorted(f"ci/{f.name}" for f in CHART.glob("ci/*.yaml")),
    ],
)
def test_every_values_file_the_repository_ships_validates_and_renders(file: str) -> None:
    """values.yaml needs the tags; the minikube values and each fixture set their own."""
    extra = TAGS if file == "values.yaml" else ()
    result = template("-f", str(CHART / file), *extra, tags=False)
    assert result.returncode == 0, result.stderr


def test_every_object_in_the_schema_refuses_keys_it_does_not_know() -> None:
    maps = {"ingress.annotations", "quickLinks.clusters", "definitions.stringMap"}
    for path, node in schema_nodes(SCHEMA):
        if node.get("type") == "object" or "properties" in node:
            expected = node.get("additionalProperties")
            if path in maps:
                assert isinstance(expected, dict), f"{path}: a map's values have a schema"
            else:
                assert expected is False, f"{path or 'the root'} accepts unknown keys"


@pytest.mark.parametrize("path", OBJECTS, ids=lambda p: p or "root")
def test_a_typo_fails_with_its_key_named(tmp_path: Path, path: str) -> None:
    pointer = "/" + path.replace(".", "/") if path else ""
    assert_refused(tmp_path, nested(path, {"typo": True}), f"at '{pointer}'", "'typo' not allowed")


@pytest.mark.parametrize(
    ("values", "pointer"),
    [
        ({"quickLinks": {"sections": [{"name": "Tools", "typo": 1}]}}, "/quickLinks/sections/0"),
        (
            {
                "quickLinks": {
                    "sections": [{"name": "Tools", "links": [{"name": "A", "href": "x"}]}]
                }
            },
            "/quickLinks/sections/0/links/0",
        ),
        ({"quickLinks": {"clusters": {"hub": {"api": "https://x"}}}}, "/quickLinks/clusters/hub"),
    ],
)
def test_a_typo_in_the_links_fails_with_its_place_named(
    tmp_path: Path, values: dict[str, Any], pointer: str
) -> None:
    assert_refused(tmp_path, values, f"at '{pointer}'", "not allowed")


@pytest.mark.parametrize(("values", "pointer", "word"), WRONG, ids=[w[1] for w in WRONG])
def test_a_wrong_type_enum_range_or_pattern_fails_with_its_key_named(
    tmp_path: Path, values: dict[str, Any], pointer: str, word: str
) -> None:
    assert_refused(tmp_path, values, f"at '{pointer}'", word)


def test_the_keys_older_releases_dropped_are_accepted_and_change_nothing(tmp_path: Path) -> None:
    assert render("-f", values_file(tmp_path, DEPRECATED_VALUES)) == render()
    deprecated = {
        path
        for path, node in schema_nodes(SCHEMA)
        if str(node.get("description", "")).startswith("Deprecated:")
    }
    assert deprecated == DEPRECATED_PATHS
    for path in DEPRECATED_PATHS:
        description = next(n["description"] for p, n in schema_nodes(SCHEMA) if p == path)
        assert "delete it" in description, path


def test_a_link_s_dropped_ping_and_argocd_keys_are_accepted(tmp_path: Path) -> None:
    """day1 names them on the page as unknown keys (ADR-0052); the chart still renders them."""
    link = {"name": "Wiki", "url": "https://wiki.example.internal", "ping": False, "argocd": "wiki"}
    values = {"quickLinks": {"sections": [{"name": "Tools", "links": [link]}]}}
    docs = {d["metadata"]["name"]: d for d in render("-f", values_file(tmp_path, values))}
    links = yaml.safe_load(docs["wingman-quick-links"]["data"]["links.yaml"])
    assert links["sections"][0]["links"][0] == link


@pytest.mark.parametrize("name", ["day1", "day2", "web"])
def test_an_empty_wingman_tag_fails_naming_it(name: str) -> None:
    others = [
        arg
        for other in ("day1", "day2", "web")
        if other != name
        for arg in ("--set", f"image.{other}.tag={TAG}")
    ]
    for extra in (others, [*others, "--set", f"image.{name}.tag="]):
        refused = template(*extra, tags=False)
        assert refused.returncode != 0
        assert f"image.{name}.tag is empty" in refused.stderr
        assert f"--set image.{name}.tag=3.33.0" in refused.stderr


def test_the_tests_set_the_tags_the_default_fixture_sets() -> None:
    fixture = yaml.safe_load(DEFAULT_FIXTURE.read_text(encoding="utf-8"))
    assert [arg for arg in TAGS if arg != "--set"] == [
        f"image.{name}.tag={fixture['image'][name]['tag']}" for name in ("day1", "day2", "web")
    ]
