"""The chart's nginx, Wingman's one entry point (ADR-0058).

The rendered ``nginx.conf`` keeps every path on its service, the timeouts,
the body size, gzip and the stream; nginx answers its own health and its own
502, 503 and 504 on ``/api/`` as an RFC 9457 problem (ADR-0004), and never
routes ``/metrics`` (ADR-0010). Its image is Red Hat's UBI nginx by tag and
digest. ``docs/ops/images.md`` has the podman run that checks the same
configuration in the image itself.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from wingman_core.web.errors import ErrorCode

sys.path.insert(0, str(Path(__file__).parent))
from chart_render import CHART, render, require_helm, template

require_helm("the chart's nginx tests")

API = {
    "/api/auth/": "day1",
    "/api/day1/": "day1",
    "~ ^/api/day1/clusters/[^/]+/upgrade-targets$": "day1",
    "/api/webhooks/": "day1",
    "/api/day2/": "day2",
}
UPGRADE_TARGETS = "~ ^/api/day1/clusters/[^/]+/upgrade-targets$"
DEFAULTS = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
PINNED = DEFAULTS["image"]["nginx"]


def nginx(*extra: str) -> tuple[str, dict[str, Any]]:
    """The rendered nginx.conf and the nginx Deployment."""
    docs = {f"{d['kind']}/{d['metadata']['name']}": d for d in render(*extra)}
    conf = docs["ConfigMap/wingman-nginx"]["data"]["nginx.conf"]
    return conf, docs["Deployment/wingman-nginx"]


def blocks(conf: str, keyword: str) -> dict[str, str]:
    """Each ``keyword <match> { ... }`` block's body, by its match, quotes respected."""
    found: dict[str, str] = {}
    for header in re.finditer(rf"^\s*{keyword}\s+([^{{\n]*?)\s*\{{", conf, re.MULTILINE):
        depth, i, quote = 1, header.end(), ""
        while depth:
            char = conf[i]
            if quote and char == "\\":
                i += 1
            elif quote:
                quote = "" if char == quote else quote
            elif char in "'\"":
                quote = char
            else:
                depth += {"{": 1, "}": -1}.get(char, 0)
            i += 1
        found[header.group(1)] = conf[header.end() : i - 1]
    return found


def directive(body: str, name: str) -> list[str]:
    """The values of each ``name ...;`` line in ``body``."""
    return re.findall(rf"^\s*{name}\s+([^;]*);", body, re.MULTILINE)


def test_every_path_goes_to_its_service_and_nothing_else_is_routed() -> None:
    conf, _ = nginx()
    locations = blocks(conf, "location")
    routed = {m: directive(b, "proxy_pass") for m, b in locations.items()}
    assert {m: p for m, p in routed.items() if p} == {
        **{match: [f"http://{service}"] for match, service in API.items()},
        "/": ["http://web"],
    }
    assert set(locations) == {*API, "/", "= /healthz", "@api_unavailable"}
    upstreams = {name: directive(body, "server") for name, body in blocks(conf, "upstream").items()}
    assert upstreams == {
        "day1": ["wingman-day1:8001"],
        "day2": ["wingman-day2:8002"],
        "web": ["wingman-web:3000"],
    }


def test_metrics_is_never_routed() -> None:
    """ADR-0010: /metrics stays on each service's own port, off the Route."""
    conf, _ = nginx()
    assert not [match for match in blocks(conf, "location") if "metrics" in match]


def test_the_timeouts_body_size_gzip_and_stream_are_kept() -> None:
    conf, _ = nginx()
    locations = blocks(conf, "location")
    assert directive(conf, "proxy_read_timeout") == ["60s", "130s"]
    assert directive(locations[UPGRADE_TARGETS], "proxy_read_timeout") == ["130s"]
    assert directive(conf, "proxy_connect_timeout") == ["10s"]
    assert directive(conf, "client_max_body_size") == ["10m"]
    assert directive(conf, "gzip") == ["on"]
    gzip_types = directive(conf, "gzip_types")[0].split()
    assert {"application/json", "application/problem+json"} <= set(gzip_types)
    assert "text/event-stream" not in gzip_types, "live status is a stream"
    # day1's stream sends X-Accel-Buffering: no; nginx must keep honouring it.
    assert not directive(conf, "proxy_ignore_headers")
    assert not directive(conf, "proxy_buffering")


def test_nginx_answers_its_own_health_and_its_probes_ask_it() -> None:
    conf, deployment = nginx()
    health = blocks(conf, "location")["= /healthz"]
    assert directive(health, "return") == ['200 "ok\\n"']
    assert not directive(health, "proxy_pass")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    for probe in ("livenessProbe", "readinessProbe"):
        assert container[probe]["httpGet"] == {"path": "/healthz", "port": 8080}, probe


def test_the_api_answers_nginx_s_own_errors_as_problems_and_pages_do_not() -> None:
    conf, _ = nginx()
    locations = blocks(conf, "location")
    for match in API:
        assert directive(locations[match], "error_page") == ["502 503 504 @api_unavailable"], match
    assert not directive(locations["/"], "error_page"), "pages keep nginx's HTML page"
    assert not directive(conf, "proxy_intercept_errors"), "a service's own errors pass through"
    assert directive(locations["@api_unavailable"], "default_type") == ["application/problem+json"]


@pytest.mark.parametrize(
    ("status", "path", "service"),
    [
        (502, "/api/day1/clusters", "day1"),
        (503, "/api/auth/me", "day1"),
        (504, "/api/day2/teams", "day2"),
    ],
)
def test_the_problem_is_rfc_9457_with_a_code_the_web_knows(
    status: int, path: str, service: str
) -> None:
    """The body as nginx fills it: ``$status`` is the status met (error_page has no ``=``)."""
    conf, _ = nginx()
    maps = blocks(conf, "map")
    services = dict(
        re.findall(r"^\s*(\S+)\s+(\S+);", maps["$uri $wingman_api_service"], re.MULTILINE)
    )
    failures = dict(
        re.findall(r'^\s*(\S+)\s+"([^"]*)";', maps["$status $wingman_api_failure"], re.MULTILINE)
    )
    assert services["~^/api/day2/"] == "day2" and services["default"] == "day1"
    body = re.search(r"return 502 '(.*)';", blocks(conf, "location")["@api_unavailable"])
    assert body is not None
    filled = (
        body.group(1)
        .replace("\\'", "'")
        .replace("$status", str(status))
        .replace("$wingman_api_service", "day2" if path.startswith("/api/day2/") else "day1")
        .replace("$wingman_api_failure", failures.get(str(status), failures["default"]))
    )
    problem = json.loads(filled)
    code = ErrorCode(problem["code"])
    assert problem == {
        "type": f"/problems/{code.slug}",
        "title": code.title,
        "status": status,
        "detail": problem["detail"],
        "code": "DEPENDENCY_UNAVAILABLE",
        "details": {},
    }
    assert f"Wingman's {service} service" in problem["detail"]
    assert f"wingman-{service} pods" in problem["detail"]


def test_nginx_logs_to_the_container_writes_only_its_emptydir_and_hides_its_version() -> None:
    conf, deployment = nginx()
    assert directive(conf, "error_log") == ["/dev/stderr"]
    assert directive(conf, "access_log") == ["/dev/stdout", "off"]
    assert directive(conf, "server_tokens") == ["off"]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    writable = next(m["mountPath"] for m in container["volumeMounts"] if m["name"] == "tmp")
    assert directive(conf, "pid") == [f"{writable}/nginx.pid"]
    temp_paths = re.findall(r"^\s*\w+_temp_path\s+(\S+);", conf, re.MULTILINE)
    assert len(temp_paths) == 5
    assert all(path.startswith(f"{writable}/") for path in temp_paths)
    # The UBI image's own command is an S2I usage note.
    assert container["command"] == ["nginx", "-e", "/dev/stderr", "-g", "daemon off;"]


def test_the_image_is_ubi_nginx_by_tag_and_digest() -> None:
    _, deployment = nginx()
    image = deployment["spec"]["template"]["spec"]["containers"][0]["image"]
    assert image == f"{PINNED['repository']}:{PINNED['tag']}@{PINNED['digest']}"
    assert PINNED["repository"] == "registry.access.redhat.com/ubi9/nginx-124"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", PINNED["digest"])


def test_the_helper_s_copy_of_the_pin_is_values_yaml_s() -> None:
    """``wingman.nginxImage`` repeats the pin to tell a kept tag from it."""
    helpers = (CHART / "templates/_helpers.tpl").read_text(encoding="utf-8")
    pattern = r'\$pinned := dict "repository" "([^"]+)" "tag" "([^"]+)" "digest" "([^"]+)"'
    pinned = re.search(pattern, helpers)
    assert pinned is not None
    assert pinned.groups() == (PINNED["repository"], PINNED["tag"], PINNED["digest"])


def test_image_registry_prefixes_nginx_and_a_mirror_keeps_the_digest() -> None:
    mirror = ["--set", "image.registry=mirror.example/wingman"]
    mirror += ["--set", "image.nginx.repository=ubi9/nginx-124"]
    _, deployment = nginx(*mirror)
    image = deployment["spec"]["template"]["spec"]["containers"][0]["image"]
    assert image == f"mirror.example/wingman/ubi9/nginx-124:{PINNED['tag']}@{PINNED['digest']}"


def test_a_tag_kept_beside_the_chart_s_digest_fails_and_an_empty_digest_pulls_by_tag() -> None:
    """``--reset-then-reuse-values`` keeps an older release's nginx and takes the chart's digest."""
    kept = ["--set", "image.nginx.repository=docker.io/nginxinc/nginx-unprivileged"]
    kept += ["--set", "image.nginx.tag=1.29.8-alpine"]
    refused = template(*kept)
    assert refused.returncode != 0
    assert (
        'image.nginx.tag is "1.29.8-alpine" but image.nginx.digest is the chart' in refused.stderr
    )
    _, deployment = nginx(*kept, "--set", "image.nginx.digest=")
    image = deployment["spec"]["template"]["spec"]["containers"][0]["image"]
    assert image == "docker.io/nginxinc/nginx-unprivileged:1.29.8-alpine"
