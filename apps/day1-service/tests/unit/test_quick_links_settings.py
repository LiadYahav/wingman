"""Quick Links' settings (ADR-0052): domains fall back, patterns and names are checked at start."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from wingman_day1.settings import MIN_DEV_AUTH_SECRET_LENGTH, Day1Settings

QUICK_LINKS_ENV = (
    "MCE_API_DOMAIN",
    "QUICK_LINKS_FILE",
    "QUICK_LINKS_HUB_NAME",
    "QUICK_LINKS_HUB_DOMAIN",
    "QUICK_LINKS_DOMAIN",
    "QUICK_LINKS_ARGOCD_URL_TEMPLATE",
    "QUICK_LINKS_CONSOLE_URL_TEMPLATE",
    "QUICK_LINKS_STATUS_ENABLED",
    "QUICK_LINKS_STATUS_TTL_SECONDS",
    "QUICK_LINKS_TIMEOUT_SECONDS",
    "QUICK_LINKS_CONCURRENCY",
    "QUICK_LINKS_SSL_VERIFY",
    "QUICK_LINKS_ARGOCD_TOKENS_FILE",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in QUICK_LINKS_ENV:
        monkeypatch.delenv(name, raising=False)


def settings(**values: object) -> Day1Settings:
    base: dict[str, object] = {
        "day1_gitlab_project_id": "42",
        "specs_gitlab_project_id": "43",
        "dev_auth_enabled": True,
        "dev_auth_secret": SecretStr("s" * MIN_DEV_AUTH_SECRET_LENGTH),
    }
    base.update(values)
    return Day1Settings(**base)  # ty: ignore[invalid-argument-type]


def test_the_defaults() -> None:
    loaded = settings()
    assert loaded.quick_links_file == Path("/etc/wingman/quick-links/links.yaml")
    assert loaded.quick_links_argocd_tokens_file == Path("/etc/wingman/argocd-tokens/tokens")
    assert loaded.quick_links_hub_name == ""
    assert loaded.quick_links_argocd_url_template == (
        "https://openshift-gitops-server-openshift-gitops.apps.{cluster}.{domain}"
    )
    assert loaded.quick_links_console_url_template == (
        "https://console-openshift-console.apps.{cluster}.{domain}"
    )
    assert loaded.quick_links_status_enabled is True
    assert loaded.quick_links_status_ttl_seconds == 60
    assert loaded.quick_links_timeout_seconds == 3
    assert loaded.quick_links_concurrency == 8
    assert loaded.quick_links_tls_verify is True


def test_the_domains_fall_back_to_the_mce_api_domain() -> None:
    loaded = settings(mce_api_domain="mgmt.example.internal.")
    assert loaded.quick_links_mce_domain == "mgmt.example.internal"
    assert loaded.quick_links_hub_base_domain == "mgmt.example.internal"
    own = settings(
        mce_api_domain="mgmt.example.internal",
        quick_links_domain="apps.example.internal",
        quick_links_hub_domain=".hub.example.internal",
    )
    assert own.quick_links_mce_domain == "apps.example.internal"
    assert own.quick_links_hub_base_domain == "hub.example.internal"
    hub_follows = settings(quick_links_domain="apps.example.internal")
    assert hub_follows.quick_links_hub_base_domain == "apps.example.internal"


def test_the_environment_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUICK_LINKS_HUB_NAME", "hub-prod")
    monkeypatch.setenv("QUICK_LINKS_SSL_VERIFY", "/etc/pki/ca.pem")
    monkeypatch.setenv("QUICK_LINKS_STATUS_ENABLED", "false")
    loaded = settings()
    assert loaded.quick_links_hub_name == "hub-prod"
    assert loaded.quick_links_tls_verify == "/etc/pki/ca.pem"
    assert loaded.quick_links_status_enabled is False


@pytest.mark.parametrize("name", ["Hub_Prod", "hub.prod", "-hub", "a" * 64])
def test_the_hub_name_is_a_cluster_name(name: str) -> None:
    with pytest.raises(ValidationError, match="QUICK_LINKS_HUB_NAME"):
        settings(quick_links_hub_name=name)


@pytest.mark.parametrize("domain", ["https://example.internal", "example internal", "a..b"])
def test_a_domain_is_a_domain(domain: str) -> None:
    with pytest.raises(ValidationError, match="must be empty or a domain"):
        settings(quick_links_domain=domain)


@pytest.mark.parametrize(
    ("template", "message"),
    [
        ("https://argocd.example.internal", "must contain"),
        ("https://{cluster}.{site}.example.internal", "may only use"),
        ("argocd-{cluster}", "http"),
    ],
)
def test_a_url_template_is_checked_at_start(template: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        settings(quick_links_argocd_url_template=template)
    with pytest.raises(ValidationError, match=message):
        settings(quick_links_console_url_template=template)


def test_the_checks_are_bounded() -> None:
    for field, value in (
        ("quick_links_status_ttl_seconds", 5),
        ("quick_links_status_ttl_seconds", 601),
        ("quick_links_timeout_seconds", 0),
        ("quick_links_timeout_seconds", 31),
        ("quick_links_concurrency", 0),
        ("quick_links_concurrency", 65),
    ):
        with pytest.raises(ValidationError):
            settings(**{field: value})
