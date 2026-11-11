"""Day1Settings fail closed (ADR-0009): nobody can log in insecurely, and somebody can log in."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from wingman_core.settings import Environment, GitBackend, RuntimeSettings
from wingman_day1.settings import (
    MIN_DEV_AUTH_SECRET_LENGTH,
    Day1Settings,
    check_runtime,
    tls_verify,
)

ENV = (
    "DAY1_GITLAB_PROJECT_ID",
    "SPECS_GITLAB_PROJECT_ID",
    "SPECS_ROOT_PATH",
    "DAY1_CLUSTER_NAME_STRIP_PREFIX",
    "MCE_CLUSTER_NAME_PREFIX",
    "OPENSHIFT_OAUTH_HOST",
    "OPENSHIFT_API_HOST",
    "OPENSHIFT_OAUTH_CLIENT_ID",
    "OPENSHIFT_OAUTH_CLIENT_SECRET",
    "OPENSHIFT_OAUTH_REDIRECT_URI",
    "DEV_AUTH_ENABLED",
    "DEV_AUTH_SECRET",
    "GITLAB_WEBHOOK_SECRET",
    "SERVER_SCAN_URL",
    "SERVER_SCAN_UI_URL",
    "SERVER_SCAN_TOKEN",
    "SERVER_SCAN_SSL_VERIFY",
    "SERVER_SCAN_TIMEOUT_SECONDS",
    "WORKFLOWS_API_URL",
    "WORKFLOWS_SSL_VERIFY",
    "WORKFLOWS_TIMEOUT_SECONDS",
    "DAY1_FAKE_FLEET",
    "SEGMENTS_MANAGER_UI_URL",
)
OAUTH = {
    "openshift_api_host": "api.hub.example.invalid:6443",
    "openshift_oauth_client_id": "wingman",
    "openshift_oauth_client_secret": SecretStr("client-secret"),
    "openshift_oauth_redirect_uri": "https://wingman.example.invalid/login",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


def settings(**values: object) -> Day1Settings:
    base: dict[str, object] = {"day1_gitlab_project_id": "42", "specs_gitlab_project_id": "43"}
    base.update(values)
    return Day1Settings(**base)  # ty: ignore[invalid-argument-type]


def dev(**values: object) -> Day1Settings:
    return settings(
        dev_auth_enabled=True,
        dev_auth_secret=SecretStr("s" * MIN_DEV_AUTH_SECRET_LENGTH),
        **values,
    )


@pytest.mark.parametrize("secret", ["", "short", "s" * (MIN_DEV_AUTH_SECRET_LENGTH - 1)])
def test_dev_login_with_a_weak_secret_refuses_to_start(secret: str) -> None:
    with pytest.raises(ValidationError, match="DEV_AUTH_SECRET"):
        settings(dev_auth_enabled=True, dev_auth_secret=SecretStr(secret))


def test_dev_login_with_a_strong_secret_starts() -> None:
    assert dev().dev_auth_enabled


def test_no_oauth_and_no_dev_login_means_nobody_could_log_in_and_is_refused() -> None:
    with pytest.raises(ValidationError, match="nobody could log in"):
        settings()


@pytest.mark.parametrize("missing", sorted(OAUTH))
def test_incomplete_oauth_is_refused_naming_what_is_missing(missing: str) -> None:
    values = {k: v for k, v in OAUTH.items() if k != missing}
    with pytest.raises(ValidationError, match=missing.upper()):
        settings(**values)


def test_complete_oauth_starts() -> None:
    loaded = settings(**OAUTH)
    assert loaded.openshift_oauth_client_secret.get_secret_value() == "client-secret"
    assert "client-secret" not in repr(loaded)


def test_the_project_ids_are_required() -> None:
    with pytest.raises(ValidationError):
        Day1Settings(dev_auth_enabled=True, dev_auth_secret=SecretStr("s" * 40))


def test_production_strips_ocp4_by_default() -> None:
    assert dev().day1_cluster_name_strip_prefix == "ocp4-"


def test_the_sandbox_sets_an_empty_prefix_through_the_new_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DAY1_CLUSTER_NAME_STRIP_PREFIX", "")
    assert dev().day1_cluster_name_strip_prefix == ""


def test_the_charts_legacy_variable_still_sets_the_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCE_CLUSTER_NAME_PREFIX", "ocp5-")
    assert dev().day1_cluster_name_strip_prefix == "ocp5-"


@pytest.mark.parametrize("prefix", ["ocp4", "-", "ocp 4-", "ocp4/-"])
def test_a_prefix_that_is_not_a_name_prefix_is_refused(prefix: str) -> None:
    with pytest.raises(ValidationError, match="DAY1_CLUSTER_NAME_STRIP_PREFIX"):
        dev(day1_cluster_name_strip_prefix=prefix)


@pytest.mark.parametrize("root", ["../specs", "/specs", "a//b"])
def test_the_specs_root_must_be_a_repository_path(root: str) -> None:
    with pytest.raises(ValidationError):
        dev(specs_root_path=root)


def test_a_nested_specs_root_is_accepted() -> None:
    assert dev(specs_root_path="catalog/specs").specs_root_path == "catalog/specs"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("No", False),
        ("/etc/pki/ca.pem", "/etc/pki/ca.pem"),
        (" /ca.pem ", "/ca.pem"),
    ],
)
def test_tls_verify_reads_the_legacy_ssl_verify_format(value: str, expected: bool | str) -> None:
    assert tls_verify(value) == expected


def test_tls_settings_are_verified_by_default() -> None:
    loaded = dev(mce_ssl_verify="false", openshift_ssl_verify="/ca.pem")
    assert dev().mce_tls_verify is True
    assert dev().openshift_tls_verify is True
    assert loaded.mce_tls_verify is False
    assert loaded.openshift_tls_verify == "/ca.pem"


def test_bounded_settings_refuse_values_out_of_range() -> None:
    with pytest.raises(ValidationError):
        dev(day1_cache_ttl_seconds=61)
    with pytest.raises(ValidationError):
        dev(day1_status_poll_seconds=1)


def test_settings_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DAY1_GITLAB_PROJECT_ID", "gitops-day1/platform-config")
    monkeypatch.setenv("SPECS_GITLAB_PROJECT_ID", "wingman/cluster-specs")
    monkeypatch.setenv("DEV_AUTH_ENABLED", "true")
    monkeypatch.setenv("DEV_AUTH_SECRET", "e" * 40)
    monkeypatch.setenv("MCE_TOKENS_FILE", str(tmp_path / "tokens"))
    loaded = Day1Settings()
    assert loaded.day1_gitlab_project_id == "gitops-day1/platform-config"
    assert loaded.mce_tokens_file == tmp_path / "tokens"
    assert not loaded.cluster_status_enabled


# ── Cluster nodes: server-scan and the orchestrator (ADR-0038) ───────────────

SERVER_SCAN = "http://server-scan-api.inventory.svc:8000"
WORKFLOWS = "http://workflows-orchestrator-api.redbull-workflows.svc:8080"


def test_cluster_nodes_are_off_by_default() -> None:
    loaded = dev()
    assert (loaded.server_scan_url, loaded.workflows_api_url, loaded.day1_fake_fleet) == (
        "",
        "",
        False,
    )
    assert loaded.server_scan_token.get_secret_value() == ""
    assert (loaded.server_scan_tls_verify, loaded.workflows_tls_verify) == (True, True)
    assert (loaded.server_scan_timeout_seconds, loaded.workflows_timeout_seconds) == (10.0, 10.0)


def test_node_links_point_at_the_api_unless_the_ui_has_its_own_url() -> None:
    assert dev(server_scan_url=SERVER_SCAN + "/").server_scan_ui_base == SERVER_SCAN
    ui = dev(server_scan_url=SERVER_SCAN, server_scan_ui_url="https://server-scan.example/")
    assert ui.server_scan_ui_base == "https://server-scan.example"


URL_SETTINGS = [
    "server_scan_url",
    "server_scan_ui_url",
    "workflows_api_url",
    "segments_manager_ui_url",
]


@pytest.mark.parametrize("field", URL_SETTINGS)
@pytest.mark.parametrize("url", ["server-scan", "ftp://server-scan.example", "http://"])
def test_a_url_setting_is_empty_or_an_http_url(field: str, url: str) -> None:
    values = {"server_scan_url": SERVER_SCAN, field: url}
    with pytest.raises(ValidationError, match="http"):
        dev(**values)


def test_the_orchestrator_without_server_scan_is_refused() -> None:
    with pytest.raises(ValidationError, match="WORKFLOWS_API_URL needs SERVER_SCAN_URL"):
        dev(workflows_api_url=WORKFLOWS)
    assert dev(workflows_api_url=WORKFLOWS, server_scan_url=SERVER_SCAN).workflows_api_url
    assert dev(workflows_api_url=WORKFLOWS, day1_fake_fleet=True).day1_fake_fleet


def test_the_server_scan_token_is_a_secret() -> None:
    loaded = dev(server_scan_url=SERVER_SCAN, server_scan_token=SecretStr("viewer-token-0001"))
    assert "viewer-token-0001" not in repr(loaded)


def test_the_tls_settings_take_the_ssl_verify_format() -> None:
    loaded = dev(server_scan_ssl_verify="false", workflows_ssl_verify="/etc/pki/ca.pem")
    assert (loaded.server_scan_tls_verify, loaded.workflows_tls_verify) == (
        False,
        "/etc/pki/ca.pem",
    )


def test_the_timeouts_are_bounded() -> None:
    with pytest.raises(ValidationError):
        dev(server_scan_timeout_seconds=0)
    with pytest.raises(ValidationError):
        dev(workflows_timeout_seconds=61)


@pytest.mark.parametrize("environment", [Environment.PRODUCTION, Environment.TEST])
def test_the_fake_fleet_is_refused_outside_development(environment: Environment) -> None:
    runtime = RuntimeSettings(environment=environment, git_backend=GitBackend.GITLAB)
    with pytest.raises(ValueError, match="DAY1_FAKE_FLEET=true is refused"):
        check_runtime(dev(day1_fake_fleet=True), runtime)


def test_the_fake_fleet_runs_in_development_with_either_git_backend() -> None:
    for backend in GitBackend:
        runtime = RuntimeSettings(environment=Environment.DEVELOPMENT, git_backend=backend)
        check_runtime(dev(day1_fake_fleet=True), runtime)
    check_runtime(dev(), RuntimeSettings(environment=Environment.PRODUCTION))


def test_the_nodes_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "DAY1_GITLAB_PROJECT_ID": "42",
        "SPECS_GITLAB_PROJECT_ID": "43",
        "DEV_AUTH_ENABLED": "true",
        "DEV_AUTH_SECRET": "e" * 40,
        "SERVER_SCAN_URL": SERVER_SCAN,
        "SERVER_SCAN_UI_URL": "https://server-scan.example",
        "SERVER_SCAN_TOKEN": "viewer-token-0001",
        "SERVER_SCAN_SSL_VERIFY": "false",
        "SERVER_SCAN_TIMEOUT_SECONDS": "20",
        "WORKFLOWS_API_URL": WORKFLOWS,
        "WORKFLOWS_SSL_VERIFY": "/ca.pem",
        "WORKFLOWS_TIMEOUT_SECONDS": "5",
        "DAY1_FAKE_FLEET": "true",
    }.items():
        monkeypatch.setenv(name, value)
    loaded = Day1Settings()
    assert loaded.server_scan_url == SERVER_SCAN
    assert loaded.server_scan_ui_base == "https://server-scan.example"
    assert loaded.server_scan_token.get_secret_value() == "viewer-token-0001"
    assert (loaded.server_scan_tls_verify, loaded.server_scan_timeout_seconds) == (False, 20.0)
    assert loaded.workflows_api_url == WORKFLOWS
    assert (loaded.workflows_tls_verify, loaded.workflows_timeout_seconds) == ("/ca.pem", 5.0)
    assert loaded.day1_fake_fleet


# ── The link to segments-manager on the cluster page ─────────────────────────

SEGMENTS_MANAGER = "https://segments-manager.example"


def test_the_segments_manager_link_is_off_by_default() -> None:
    assert dev().segments_manager_ui_url == ""


def test_the_segments_manager_url_loses_its_trailing_slash() -> None:
    loaded = dev(segments_manager_ui_url=f"  {SEGMENTS_MANAGER}/ ")
    assert loaded.segments_manager_ui_url == SEGMENTS_MANAGER


def test_the_segments_manager_link_needs_nothing_else(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only a link: no server-scan, no orchestrator, no token."""
    for name, value in {
        "DAY1_GITLAB_PROJECT_ID": "42",
        "SPECS_GITLAB_PROJECT_ID": "43",
        "DEV_AUTH_ENABLED": "true",
        "DEV_AUTH_SECRET": "e" * 40,
        "SEGMENTS_MANAGER_UI_URL": SEGMENTS_MANAGER + "/",
    }.items():
        monkeypatch.setenv(name, value)
    loaded = Day1Settings()
    assert loaded.segments_manager_ui_url == SEGMENTS_MANAGER
    assert (loaded.server_scan_url, loaded.workflows_api_url) == ("", "")
