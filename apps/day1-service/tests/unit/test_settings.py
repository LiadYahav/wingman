"""Day1Settings fail closed (ADR-0009): nobody can log in insecurely, and somebody can log in."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from wingman_day1.settings import MIN_DEV_AUTH_SECRET_LENGTH, Day1Settings, tls_verify

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
