"""The living docs name only routes, settings, error codes and Helm keys that exist.

The in-app docs page, the READMEs and DEVELOPMENT.md were written for the
legacy services and kept describing routes, variables and Helm keys the
rewrite removed or renamed, because nothing compared them with the code.
These tests read the docs' source and compare what they name with the code:

- every ``METHOD /path`` (inline or in a README table row) and every bare
  ``/api/...`` path with the routes both services serve, built on the fake
  backend from explicit settings; the README's API tables in both directions;
- every SCREAMING_CASE name, and a single upper-case word in a code span or
  before ``=``, with what a settings class reads, a problem ``code``
  (ADR-0004) or the short ``NOT_SETTINGS`` allowlist;
- every ``<status> <CODE>`` with that code's status in ``wingman_core.web.errors``;
- every Helm key with ``deploy/helm/wingman/values.yaml``, and every key-to-variable pair
  with what ``deploy/helm/wingman/templates/configmap.yaml`` and ``secret.yaml`` set,
  and the ``env`` entries of its ``*-deployment.yaml`` templates;
- and nothing the rewrite removed (``REMOVED``) comes back.

Guarded: ``README.md``, ``DEVELOPMENT.md``, ``deploy/helm/wingman/README.md``,
``apps/web/README.md``, ``docs/ops/*.md`` and every file under
``apps/web/app/(app)/docs/``. Left out on purpose: ``docs/adr/`` and
``docs/notes/`` (history: they name what was true when they were written) and
``docs/upgrade/`` (a migration guide that names the removed settings on
purpose); so are ``CLAUDE.md`` and ``docs/ecosystem/README.md``, which name the
legacy code on purpose. Every check also asserts it found what it must find,
so a parser that stops matching fails instead of passing on nothing.
"""

from __future__ import annotations

import inspect
import itertools
import re
import sys
from collections.abc import Callable, Mapping
from functools import cache
from pathlib import Path
from typing import NamedTuple

import pytest
import yaml
from pydantic import SecretStr

import wingman_core.web.errors as problem_types
from wingman_core.settings import AuthSettings, Environment, GitBackend, RuntimeSettings
from wingman_core.web.errors import AppError, ErrorCode
from wingman_day1.main import create_app as create_day1
from wingman_day1.settings import Day1Settings
from wingman_day2.main import create_app as create_day2
from wingman_day2.settings import Config, Day2Settings

sys.path.insert(0, str(Path(__file__).parent))
from service_settings import read_by_services

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
CHART = ROOT / "deploy/helm/wingman"
CHART_README = CHART / "README.md"
PAGE_DIR = ROOT / "apps/web/app/(app)/docs"
MARKDOWN: tuple[Path, ...] = (
    README,
    ROOT / "DEVELOPMENT.md",
    CHART_README,
    ROOT / "apps/web/README.md",
    *sorted((ROOT / "docs/ops").glob("*.md")),
)
PAGE_FILES: tuple[Path, ...] = tuple(sorted(p for p in PAGE_DIR.rglob("*") if p.is_file()))
PAGE = "apps/web/app/(app)/docs/"
"""The docs page, every file of it read as one text."""
DOCS: tuple[str, ...] = (*(str(p.relative_to(ROOT)) for p in MARKDOWN), PAGE)


def read(doc: str) -> str:
    """A guarded doc's text; the docs page is every file under its folder."""
    if doc == PAGE:
        return "\n".join(p.read_text(encoding="utf-8") for p in PAGE_FILES)
    return (ROOT / doc).read_text(encoding="utf-8")


# ── What the rewrite removed ──────────────────────────────────────────────────


class Removed(NamedTuple):
    """Something no living doc may name again, and a sample that proves the pattern bites."""

    what: str
    pattern: re.Pattern[str]
    sample: str


REMOVED: tuple[Removed, ...] = (
    Removed(
        "GET /cache/stats (ADR-0011)", re.compile(r"/cache/stats"), "GET /api/day1/cache/stats"
    ),
    Removed(
        "POST /sites (ADR-0018)",
        re.compile(r"POST\s+(?:/api/day1)?/sites(?![/\w])"),
        "POST /sites",
    ),
    Removed(
        "POST /sites/{site}/mces (ADR-0018)",
        re.compile(r"POST\s+(?:/api/day1)?/sites/\{site\}/mces"),
        "POST /api/day1/sites/{site}/mces",
    ),
    # POST /clusters/{name}/sync is back with another meaning: sync to the flavor (ADR-0037).
    Removed(
        "sync-yaml and its Sync button (ADR-0016)",
        re.compile(r"sync[-_ ]?yaml", re.IGNORECASE),
        "the Sync YAML button",
    ),
    Removed(
        "GET /api/auth/login (login starts at GET /api/auth/config)",
        re.compile(r"/api/auth/login\b"),
        "GET /api/auth/login",
    ),
    Removed(
        "GITLAB_ACCESS_TOKEN (now GITLAB_TOKEN)",
        re.compile(r"\bGITLAB_ACCESS_TOKEN\b"),
        "GITLAB_ACCESS_TOKEN",
    ),
    Removed(
        "GITLAB_DAY1_TOKEN, GITLAB_DAY2_TOKEN, GITLAB_SPECS_TOKEN (one GITLAB_TOKEN now)",
        re.compile(r"\bGITLAB_(?:DAY1|DAY2|SPECS)_TOKEN\b"),
        "--from-literal=GITLAB_SPECS_TOKEN=x",
    ),
    Removed(
        "GITLAB_SSL_VERIFY (now GITLAB_VERIFY_TLS)",
        re.compile(r"\bGITLAB_SSL_VERIFY\b"),
        "GITLAB_SSL_VERIFY",
    ),
    Removed(
        "OAUTH_CLIENT_SECRET (now OPENSHIFT_OAUTH_CLIENT_SECRET)",
        re.compile(r"(?<![A-Z0-9_])OAUTH_CLIENT_SECRET\b"),
        "--from-literal=OAUTH_CLIENT_SECRET=x",
    ),
    Removed("LOG_LEVEL (nothing reads it)", re.compile(r"(?<![A-Z0-9_])LOG_LEVEL\b"), "LOG_LEVEL"),
    Removed(
        "the legacy CACHE_* variables (ADR-0011)",
        re.compile(r"(?<![A-Z0-9_])CACHE_[A-Z0-9_*]+"),
        "`CACHE_*_TTL`",
    ),
    Removed(
        "the legacy *_PATH_TEMPLATE variables (ADR-0020)",
        re.compile(r"[A-Z0-9_]+_PATH_TEMPLATE\b"),
        "DAY1_CLUSTERS_PATH_TEMPLATE",
    ),
    Removed(
        "the legacy entry point src.main:app",
        re.compile(r"src\.main:app"),
        "uv run uvicorn src.main:app",
    ),
    Removed(
        "the legacy src/routers and src/services",
        re.compile(r"\bsrc/(?:routers|services)/"),
        "in `src/routers/<domain>.py`",
    ),
    Removed(
        "wingman_shared and packages/shared-python (removed)",
        re.compile(r"\bwingman_shared\b|shared-python"),
        "packages/shared-python",
    ),
    Removed(
        "the legacy GitLabClient, CacheManager and aread_file",
        re.compile(r"\b(?:GitLabClient|CacheManager|aread_file)\b"),
        "await gl.aread_file(path)",
    ),
    Removed(
        "python-gitlab (GitLabPort over httpx, ADR-0002)",
        re.compile(r"\bpython-gitlab\b"),
        "FastAPI, python-gitlab",
    ),
    Removed(
        "mypy (ty now, ADR-0008)", re.compile(r"\bmypy\b"), "cd apps/day1-service && mypy src/"
    ),
    Removed(
        "creating wingman-secrets by hand (the chart renders it)",
        re.compile(r"create\s+secret\s+generic\s+wingman-secrets"),
        "oc create secret generic wingman-secrets",
    ),
    Removed(
        "day2 chart dependencies (always [] now)",
        re.compile(
            r"\b(?:addon|chart|day2)\s+dependenc(?:y|ies)\b|\bdependency\s+chips?\b|\bdependencies\s*:",
            re.IGNORECASE,
        ),
        "dependency chips",
    ),
)


def removed_mentions(text: str) -> list[str]:
    """``"<what>: <match>"`` for every removed thing ``text`` still mentions."""
    return [
        f"{removed.what}: {match.group(0)!r}"
        for removed in REMOVED
        for match in removed.pattern.finditer(text)
    ]


# ── Routes ────────────────────────────────────────────────────────────────────

HIDDEN_ROUTES = frozenset(
    {("GET", "/health/live"), ("GET", "/healthz"), ("GET", "/health/ready"), ("GET", "/metrics")}
)
"""What ``create_base_app`` adds with ``include_in_schema=False`` (health and metrics)."""
METHOD = r"(GET|POST|PUT|PATCH|DELETE)"
INLINE_ROUTE = re.compile(METHOD + r"\s+`?(/[\w{}/.\-]*)")
TABLE_ROUTE = re.compile(r"^\|\s*`" + METHOD + r"`\s*\|\s*`(/[^`]*)`\s*\|", re.MULTILINE)
BARE_API_PATH = re.compile(r"(?<![\w/.\-])(/api(?:/[\w{}.\-*:]*)*)")
PARAM = re.compile(r"\{[^}]*\}")


@cache
def served_routes() -> frozenset[tuple[str, str]]:
    """Every ``(method, path)`` day1 and day2 serve.

    Both apps are built on the fake backend from settings made here
    (``model_construct``: no environment is read). Routes come from
    ``app.openapi()``: walking ``app.routes`` misses what included routers add.
    """
    secret = SecretStr("docs-contract-secret-" + "x" * 32)
    runtime = RuntimeSettings.model_construct(
        environment=Environment.DEVELOPMENT, git_backend=GitBackend.FAKE
    )
    auth = AuthSettings.model_construct(jwt_secret_key=secret)
    day1 = create_day1(
        settings=Day1Settings.model_construct(
            day1_gitlab_project_id="gitops-day1/platform-config",
            specs_gitlab_project_id="wingman/cluster-specs",
        ),
        auth=auth,
        runtime=runtime,
    )
    day2 = create_day2(
        Config(
            runtime=runtime,
            auth=auth,
            day2=Day2Settings.model_construct(
                day2_sigs_group_path="sigs", day1_gitlab_project_id="gitops-day1/platform-config"
            ),
            gitlab=None,
        )
    )
    routes = set(HIDDEN_ROUTES)
    for app in (day1, day2):
        paths = {getattr(route, "path", None) for route in app.routes}
        assert {path for _, path in HIDDEN_ROUTES} <= paths, "HIDDEN_ROUTES is out of date"
        for path, operations in app.openapi()["paths"].items():
            routes |= {(method.upper(), path) for method in operations}
    return frozenset(routes)


def shape(path: str) -> str:
    """Path parameters by position only: ``/clusters/{name}`` is ``/clusters/{cluster}``."""
    return PARAM.sub("{}", path.split("?")[0].rstrip("/") or "/")


def served_shapes() -> set[tuple[str, str]]:
    return {(method, shape(path)) for method, path in served_routes()}


def routes_named(text: str) -> set[tuple[str, str]]:
    """``METHOD /path`` mentions of the services' paths, inline or as table rows."""
    named = {(m, p) for m, p in TABLE_ROUTE.findall(text)}
    for method, path in INLINE_ROUTE.findall(text):
        path = path.rstrip(".")
        if path.startswith("/api/") or (method, path) in HIDDEN_ROUTES:
            named.add((method, path))
    return named


def unknown_routes(text: str) -> list[str]:
    """Every ``METHOD /path`` that neither service serves."""
    shapes = served_shapes()
    return sorted(f"{m} {p}" for m, p in routes_named(text) if (m, shape(p)) not in shapes)


def unknown_api_paths(text: str) -> list[str]:
    """Every bare ``/api/...`` path that is not a route or the start of one."""
    served = [shape(path).split("/") for _, path in served_routes()]
    unknown = set()
    for found in BARE_API_PATH.findall(text):
        path = re.sub(r"(?:/:path\*|/\*|\*|/\.\.\.|\.+)$", "", found)
        segments = shape(path).split("/")
        if not any(route[: len(segments)] == segments for route in served):
            unknown.add(found)
    return sorted(unknown)


# ── Settings, codes and other upper-case names ────────────────────────────────

SCREAMING_CASE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
MARKDOWN_SPAN = re.compile(r"`([^`\n]+)`")
TSX_SPAN = re.compile(r"<InlineCode>([^<]*)</InlineCode>")
SINGLE_WORD = re.compile(r"[A-Z][A-Z0-9]+")
ASSIGNED = re.compile(r"(?<![\w$.\-])([A-Z][A-Z0-9]+)=")
DEFINED_IN_PAGE = re.compile(r"\b(?:const|let|function)\s+([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*)\b")

NOT_SETTINGS: Mapping[str, str] = {
    "SSL_CERT_FILE": "httpx and ssl (the chart sets it with tls.caBundle)",
    "PYTHON_BUILD_STANDALONE_URL": "a build argument of the service Dockerfiles",
    "VERSION": "a build argument of every Dockerfile",
    "COMMIT": "a build argument of every Dockerfile",
    "SHA": "the shell variable the build instructions set",
    "SHA256SUMS": "python-build-standalone's checksum file",
    "HEAD": "Git's",
    "ROUTERS": "day1's router tuple in main.py",
    "FROM": "a Dockerfile instruction",
    "CMD": "a Dockerfile instruction",
    "MCE": "the create form's field label, on the docs page",
    "AVAILABLE": "server-scan's openshift_state of a server in no MCE (Inventory, ADR-0057)",
    "INSTALLED_TO_INVENTORY": "server-scan's openshift_state of an MCE's free Agent (ADR-0057)",
    **dict.fromkeys(METHOD.strip("()").split("|"), "an HTTP method"),
}
"""Upper-case names the docs may show that no settings class reads, and what they are."""
NOT_SETTINGS_PREFIXES: Mapping[str, str] = {
    "PLAYWRIGHT_": "Playwright (apps/web/playwright.config.ts)",
    "WINGMAN_DEV_": "the web dev server (next.config.ts) and the live e2e specs",
    "WINGMAN_TEST_GITLAB_": "the live GitLab contract (pyproject.toml's live_gitlab marker)",
}


def names_in(text: str, *, tsx: bool) -> set[str]:
    """The settings-like names ``text`` shows.

    Every SCREAMING_CASE name with an underscore; a single upper-case word only
    in a code span or before ``=``, where it is a name (prose has YAML, VLAN...).
    """
    spans = (TSX_SPAN if tsx else MARKDOWN_SPAN).findall(text)
    names = set(SCREAMING_CASE.findall(text)) | set(ASSIGNED.findall(text))
    names |= {span.strip() for span in spans if SINGLE_WORD.fullmatch(span.strip())}
    if tsx:
        names -= set(DEFINED_IN_PAGE.findall(text))
    return names


def unknown_names(text: str, *, tsx: bool) -> list[str]:
    known = set(read_by_services()) | {code.value for code in ErrorCode} | set(NOT_SETTINGS)
    return sorted(
        name
        for name in names_in(text, tsx=tsx) - known
        if not name.startswith(tuple(NOT_SETTINGS_PREFIXES))
    )


# ── Problem statuses ──────────────────────────────────────────────────────────

REFUSAL = re.compile(r'\bcode:\s*"([^"]*)"')
STATUS_SPAN = re.compile(r"([1-5]\d\d) ([A-Z][A-Z0-9_]*)")
STATUS_AND_CODE = re.compile(r"(?<!\d)([1-5]\d\d)\s+`?([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*)(?![\w*])")


@cache
def problem_statuses() -> Mapping[str, int]:
    """Each ``ErrorCode``'s HTTP status, from the ``AppError`` classes."""
    statuses: dict[str, set[int]] = {}
    for _, cls in inspect.getmembers(problem_types, inspect.isclass):
        if issubclass(cls, AppError):
            statuses.setdefault(cls.code.value, set()).add(cls.status)
    assert all(len(s) == 1 for s in statuses.values()), f"a code has two statuses: {statuses}"
    return {code: status for code, (status,) in statuses.items()}


def refusals(text: str) -> list[str]:
    """The docs page's ``code: "<status> <CODE>"`` entries."""
    return REFUSAL.findall(text)


def wrong_statuses(text: str, *, tsx: bool) -> list[str]:
    """Every ``<status> <CODE>`` whose code has another status, or does not exist.

    An unknown code is caught where the pair stands alone (a page refusal, or a
    code span such as `` `409 REVISION_CONFLICT` ``); elsewhere an unknown
    SCREAMING_CASE code is the names check's.
    """
    statuses = problem_statuses()
    spans = (TSX_SPAN if tsx else MARKDOWN_SPAN).findall(text)
    standalone = [*refusals(text), *(s.strip() for s in spans if STATUS_SPAN.fullmatch(s.strip()))]
    wrong = []
    for pair in standalone:
        found = STATUS_SPAN.fullmatch(pair)
        if found is None or statuses.get(found[2]) != int(found[1]):
            code = found[2] if found else pair
            wrong.append(f"{pair!r} (the code's status: {statuses.get(code)})")
    for status, code in STATUS_AND_CODE.findall(text):
        if code in statuses and statuses[code] != int(status):
            wrong.append(f"{status} {code} (the code's status: {statuses[code]})")
    return sorted(set(wrong))


# ── Helm keys ─────────────────────────────────────────────────────────────────

HELM_KEY = r"[a-z][A-Za-z0-9]*(?:\.(?:[A-Za-z0-9]+|<[^>]+>|\{[A-Za-z0-9,]+\}))*"
SET_FLAG = re.compile(r"--set(?:-string)?\s+(" + HELM_KEY + r")=")
CHART_TABLE_ROW = re.compile(r"^\|\s*`(" + HELM_KEY + r")`\s*\|([^|\n]*)\|", re.MULTILINE)
HELM_TO_ENV = re.compile(
    r"Helm:?\s*(?:<InlineCode>)?(" + HELM_KEY + r")(?:</InlineCode>)?\s*→\s*(?:env:\s*)?"
    r"(?:<InlineCode>)?([A-Z][A-Z0-9_]*)"
)
FILE_NAME = re.compile(r"\.(?:py|tsx?|ya?ml|md|json|txt|j2|sh|toml|tpl)$")
CHART_ENV_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*):\s*(\{\{.*\}\})", re.MULTILINE)
CHART_ENV_ENTRY = re.compile(r"^( *)- name: ([A-Z][A-Z0-9_]*)\n((?:\1  .*\n)+)", re.MULTILINE)
"""A container's ``env`` entry: ``- name: NAME`` and the lines indented under it."""
VALUES_REF = re.compile(r"\.Values\.([\w.]+)")
INCLUDE = re.compile(r'include\s+"([\w.]+)"')


@cache
def values_paths() -> Mapping[str, object]:
    """Every key path in the chart's ``values.yaml`` (``gitlab.url``, ...), with its default."""
    paths: dict[str, object] = {}

    def walk(node: Mapping[str, object], prefix: str) -> None:
        for key, value in node.items():
            paths[prefix + key] = value
            if isinstance(value, dict):
                walk(value, f"{prefix}{key}.")

    walk(yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8")), "")
    return paths


def expand(key: str) -> list[str]:
    """``image.{day1,web}.tag`` as ``image.day1.tag`` and ``image.web.tag``."""
    parts = [
        part[1:-1].split(",") if part.startswith("{") else [part]
        for part in re.split(r"(\{[^}]*\})", key)
    ]
    return ["".join(choice) for choice in itertools.product(*parts)]


def helm_key_exists(key: str) -> bool:
    """``key`` is a values path (``<x>`` matches any one key), or is under a free-form map."""
    for one in expand(key):
        pattern = re.compile(
            r"\.".join(r"[^.]+" if s.startswith("<") else re.escape(s) for s in one.split("."))
        )
        paths = values_paths()
        if any(pattern.fullmatch(path) for path in paths):
            continue
        segments = one.split(".")
        under_map = any(paths.get(".".join(segments[:n])) == {} for n in range(1, len(segments)))
        if not under_map:
            return False
    return True


def helm_keys_named(text: str, *, tsx: bool, chart_readme: bool) -> set[str]:
    """``--set`` keys, the Key Values table's keys, and code spans that are values paths."""
    top_level = {path for path in values_paths() if "." not in path}
    keys = set(SET_FLAG.findall(text)) | {key for key, _ in HELM_TO_ENV.findall(text)}
    for span in (TSX_SPAN if tsx else MARKDOWN_SPAN).findall(text):
        span = span.strip()
        if (
            re.fullmatch(HELM_KEY, span)
            and "." in span
            and span.split(".")[0] in top_level
            and not FILE_NAME.search(span)
        ):
            keys.add(span)
    if chart_readme:
        keys |= {key for key, _ in CHART_TABLE_ROW.findall(text)}
    return keys


@cache
def chart_env_sources() -> Mapping[str, frozenset[str]]:
    """Each variable the chart sets, and the values keys its template reads (helpers included).

    The ConfigMap and the Secret set most, one ``NAME: {{ ... }}`` line each; a
    Deployment's ``env`` entry sets the rest (``SERVER_SCAN_TOKEN``, from a
    ``secretKeyRef`` to an existing Secret), from the keys the entry reads.
    """
    templates = CHART / "templates"
    helpers_tpl = (templates / "_helpers.tpl").read_text(encoding="utf-8")
    pieces = re.split(r'\{\{-?\s*define\s+"([\w.]+)"', helpers_tpl)
    helpers = dict(itertools.batched(pieces[1:], 2, strict=True))

    def reads(expression: str) -> frozenset[str]:
        refs = set(VALUES_REF.findall(expression))
        for helper in INCLUDE.findall(expression):
            refs |= set(VALUES_REF.findall(helpers[helper]))
        return frozenset(refs)

    sources: dict[str, frozenset[str]] = {}
    for template in ("configmap.yaml", "secret.yaml"):
        text = (templates / template).read_text(encoding="utf-8")
        for env, expression in CHART_ENV_LINE.findall(text):
            sources[env] = reads(expression)
    for deployment in sorted(templates.glob("*-deployment.yaml")):
        text = deployment.read_text(encoding="utf-8")
        for _, env, entry in CHART_ENV_ENTRY.findall(text):
            sources[env] = reads(entry)
    return sources


def helm_env_pairs(text: str, *, chart_readme: bool) -> set[tuple[str, str]]:
    """``Helm: key → env: NAME`` on the page; ``| `key` | `NAME` |`` rows in the chart README."""
    pairs = set(HELM_TO_ENV.findall(text))
    if chart_readme:
        for key, sets in CHART_TABLE_ROW.findall(text):
            if env := re.search(r"`([A-Z][A-Z0-9_]*)`", sets):
                pairs.add((key, env.group(1)))
    return pairs


def wrong_helm(text: str, *, tsx: bool, chart_readme: bool) -> list[str]:
    """Helm keys values.yaml does not have, and pairs the chart does not set that way."""
    wrong = [
        f"{key}: not in deploy/helm/wingman/values.yaml"
        for key in helm_keys_named(text, tsx=tsx, chart_readme=chart_readme)
        if not helm_key_exists(key)
    ]
    sources = chart_env_sources()
    wrong += [
        f"{key} → {env}: the chart sets {env} from {sorted(sources.get(env, ())) or 'nothing'}"
        for key, env in helm_env_pairs(text, chart_readme=chart_readme)
        if key not in sources.get(env, ())
    ]
    return sorted(wrong)


# ── What each doc must be found to name (no vacuous pass) ─────────────────────

SENTINEL_NAMES: Mapping[str, frozenset[str]] = {
    "README.md": frozenset({"GITLAB_TOKEN", "DAY2_SIGS_GROUP_PATH", "MCE_INFRAENV_NAMESPACE"}),
    "DEVELOPMENT.md": frozenset({"DAY2_SERVICE_URL", "WINGMAN_GIT_BACKEND", "ROUTERS"}),
    "deploy/helm/wingman/README.md": frozenset({"GITLAB_TOKEN", "OPENSHIFT_OAUTH_CLIENT_SECRET"}),
    "apps/web/README.md": frozenset({"WINGMAN_DEV_DAY1_URL", "DEV_AUTH_SECRET"}),
    "docs/ops/images.md": frozenset({"WINGMAN_VERSION", "PYTHON_BUILD_STANDALONE_URL", "VERSION"}),
    "docs/ops/metrics.md": frozenset({"GITLAB_TOKEN"}),
    "docs/ops/runbook.md": frozenset({"GITLAB_TOKEN", "GITLAB_VERIFY_TLS"}),
    PAGE: frozenset({"WINGMAN_ADMIN_GROUPS", "DEV_AUTH_SECRET", "MCE_INFRAENV_NAMESPACE"}),
}
SENTINEL_PAIRS: Mapping[str, frozenset[tuple[str, str]]] = {
    PAGE: frozenset({("gitlab.day1ProjectId", "DAY1_GITLAB_PROJECT_ID")}),
    # One pair from the Secret, one from a Deployment's env entry.
    "deploy/helm/wingman/README.md": frozenset(
        {
            ("gitlab.accessToken", "GITLAB_TOKEN"),
            ("serverScan.tokenSecret.name", "SERVER_SCAN_TOKEN"),
        }
    ),
}
MIN_REFUSALS = 8
MIN_PAGE_PAIRS = 4
MIN_CHART_README_PAIRS = 25
MIN_CHART_README_KEYS = 35


def page_coverage_gaps(text: str) -> list[str]:
    """What the page checks must find on the docs page, and did not."""
    gaps = []
    if missing := SENTINEL_NAMES[PAGE] - names_in(text, tsx=True):
        gaps.append(f"names not found: {sorted(missing)}")
    if len(refusals(text)) < MIN_REFUSALS:
        gaps.append(f"fewer than {MIN_REFUSALS} refusals found")
    pairs = helm_env_pairs(text, chart_readme=False)
    if len(pairs) < MIN_PAGE_PAIRS or not SENTINEL_PAIRS[PAGE] <= pairs:
        gaps.append(f"too few Helm → env pairs found: {sorted(pairs)}")
    return gaps


def source(doc: str) -> tuple[str, bool]:
    return read(doc), doc == PAGE


# ── The tests ─────────────────────────────────────────────────────────────────


def test_every_guarded_doc_exists() -> None:
    assert PAGE_FILES, f"nothing under {PAGE}"
    assert set(SENTINEL_NAMES) <= set(DOCS), "a sentinel names a doc that is not guarded"
    assert all((ROOT / doc).is_file() for doc in DOCS if doc != PAGE)


@pytest.mark.parametrize("doc", DOCS)
def test_docs_do_not_mention_what_was_removed(doc: str) -> None:
    found = removed_mentions(read(doc))
    assert not found, f"{doc} still mentions removed features: {found}"


@pytest.mark.parametrize("doc", DOCS)
def test_every_route_a_doc_names_is_served(doc: str) -> None:
    text = read(doc)
    unknown = unknown_routes(text) + unknown_api_paths(text)
    assert not unknown, f"{doc} names routes neither service serves: {unknown}"


def test_the_readme_lists_every_route() -> None:
    text = README.read_text(encoding="utf-8")
    documented = {(m, shape(p)) for m, p in TABLE_ROUTE.findall(text)}
    assert ("GET", "/api/auth/me") in documented, "the README's API table parser found nothing"
    assert ("GET", "/api/auth/config") in routes_named(text), "the inline route parser is broken"
    undocumented = sorted(f"{m} {p}" for m, p in served_shapes() - documented)
    assert not undocumented, f"README.md's API Reference misses: {undocumented}"


def test_the_readme_names_every_setting() -> None:
    named = names_in(README.read_text(encoding="utf-8"), tsx=False)
    missing = sorted(set(read_by_services()) - named)
    assert not missing, f"README.md's Environment Variables miss: {missing}"


@pytest.mark.parametrize("doc", DOCS)
def test_every_name_a_doc_shows_is_a_setting_or_a_code(doc: str) -> None:
    text, tsx = source(doc)
    unknown = unknown_names(text, tsx=tsx)
    assert not unknown, (
        f"{doc} names settings or codes nothing defines: {unknown} "
        "(a name that is not a setting goes in NOT_SETTINGS, with what reads it)"
    )
    if missing := SENTINEL_NAMES.get(doc, frozenset()) - names_in(text, tsx=tsx):
        pytest.fail(f"the name parser no longer finds {sorted(missing)} in {doc}")


@pytest.mark.parametrize("doc", DOCS)
def test_every_status_a_doc_gives_is_its_codes(doc: str) -> None:
    text, tsx = source(doc)
    wrong = wrong_statuses(text, tsx=tsx)
    assert not wrong, f"{doc} gives codes the wrong status (wingman_core.web.errors): {wrong}"


@pytest.mark.parametrize("doc", DOCS)
def test_every_helm_key_a_doc_names_is_the_charts(doc: str) -> None:
    text, tsx = source(doc)
    wrong = wrong_helm(text, tsx=tsx, chart_readme=doc == "deploy/helm/wingman/README.md")
    assert not wrong, f"{doc} names Helm values the chart does not have: {wrong}"


def test_the_page_checks_find_what_they_must() -> None:
    gaps = page_coverage_gaps(read(PAGE))
    assert not gaps, f"the docs page checks would pass on nothing: {gaps}"


def test_the_chart_readme_checks_find_what_they_must() -> None:
    text = CHART_README.read_text(encoding="utf-8")
    pairs = helm_env_pairs(text, chart_readme=True)
    sentinels = SENTINEL_PAIRS["deploy/helm/wingman/README.md"]
    assert sentinels <= pairs, f"the table parser no longer finds {sorted(sentinels - pairs)}"
    sources = chart_env_sources()
    unset = sorted((key, env) for key, env in sentinels if key not in sources.get(env, ()))
    assert not unset, f"the template parser no longer finds {unset}"
    assert len(pairs) >= MIN_CHART_README_PAIRS, f"only {len(pairs)} key → variable pairs found"
    keys = helm_keys_named(text, tsx=False, chart_readme=True)
    assert len(keys) >= MIN_CHART_README_KEYS, f"only {len(keys)} Helm keys found"


# ── The guard bites ───────────────────────────────────────────────────────────


def test_every_removed_pattern_bites() -> None:
    """Each pattern matches its sample, so a typo cannot disable it."""
    for removed in REMOVED:
        assert removed.pattern.search(removed.sample), removed.what
    assert not removed_mentions(
        "DAY1_CACHE_TTL_SECONDS DAY2_CACHE_TTL_SECONDS OPENSHIFT_OAUTH_CLIENT_SECRET "
        "DEPENDENCY_UNAVAILABLE GET /sites GET /api/auth/config redirect to /login "
        "# Install dependencies ty check"
    )


def page_names(text: str) -> list[str]:
    return unknown_names(text, tsx=True)


def page_statuses(text: str) -> list[str]:
    return wrong_statuses(text, tsx=True)


def page_helm(text: str) -> list[str]:
    return wrong_helm(text, tsx=True, chart_readme=False)


class Mutation(NamedTuple):
    """An edit of the page that one check must refuse."""

    old: str
    new: str
    check: Callable[[str], list[str]]


PAGE_MUTATIONS: Mapping[str, Mutation] = {
    "a route neither service serves": Mutation(
        "Platform Documentation",
        "GET /api/day1/clusters/{name}/restart Platform Documentation",
        unknown_routes,
    ),
    "a bare path no route starts with": Mutation(
        "Platform Documentation",
        "<InlineCode>/api/day1/cache</InlineCode> Platform Documentation",
        unknown_api_paths,
    ),
    "a code with another code's status": Mutation(
        'code: "409 NOT_MERGEABLE"', 'code: "422 NOT_MERGEABLE"', page_statuses
    ),
    "a code that does not exist": Mutation(
        'code: "403 FORBIDDEN"', 'code: "403 DENIED"', page_statuses
    ),
    "a one-word variable": Mutation(
        "Platform Documentation", "<InlineCode>LOGLEVEL</InlineCode>", page_names
    ),
    "a variable with an underscore": Mutation(
        "Platform Documentation", "set LOG_FORMAT=json", page_names
    ),
    "a Helm key the chart does not have": Mutation(
        "gitlab.specsProjectId", "specs.gitlab.projectId", page_helm
    ),
    "a Helm key mapped to another variable": Mutation(
        "<InlineCode>gitlab.day1ProjectId</InlineCode> → env: <InlineCode>DAY1_GITLAB_PROJECT_ID",
        "<InlineCode>gitlab.day1ProjectId</InlineCode> → env: <InlineCode>SPECS_GITLAB_PROJECT_ID",
        page_helm,
    ),
    "nothing left to check": Mutation('"use client";', '"use client";', page_coverage_gaps),
}


@pytest.mark.parametrize("name", PAGE_MUTATIONS)
def test_the_page_checks_catch(name: str) -> None:
    mutation = PAGE_MUTATIONS[name]
    page = read(PAGE)
    assert not mutation.check(page), f"the check reports the page itself: {mutation.check(page)}"
    assert mutation.old in page, f"the mutation's anchor is gone from the page: {mutation.old!r}"
    mutated = page.replace(mutation.old, mutation.new)
    if name == "nothing left to check":
        mutated = mutated.lower()
    assert mutation.check(mutated), f"missed: {name}"


def markdown_problems(text: str) -> list[str]:
    return [
        *unknown_routes(text),
        *unknown_names(text, tsx=False),
        *wrong_statuses(text, tsx=False),
        *wrong_helm(text, tsx=False, chart_readme=True),
    ]


@pytest.mark.parametrize(
    "sample",
    [
        "| `GET` | `/api/day1/clusters/{name}/restart` | Restart |",
        "`POST /api/day2/clusters/{cluster}/sync`",
        "set `LOGLEVEL` to debug",
        "a `422 NOT_MERGEABLE` problem",
        "--set image.tag=$SHA",
        "| `gitlab.day1ProjectId` | `SPECS_GITLAB_PROJECT_ID` | | |",
        "| `serverScan.url` | `SERVER_SCAN_TOKEN` | | |",
        "| `global.baseDomain` | | `wingman.local` | |",
    ],
)
def test_the_markdown_checks_catch(sample: str) -> None:
    assert markdown_problems(sample), f"missed: {sample}"
