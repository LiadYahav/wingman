"""The chart sets exactly the variables the services read.

The legacy chart kept setting `GITLAB_ACCESS_TOKEN` after the core started
reading `GITLAB_TOKEN`, and a dozen `CACHE_*` names nothing read. Nothing
compared the two. These tests render the chart's ConfigMap and Secret and
compare their keys with the environment names of every settings class day1
and day2 load (ADR-0009).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from wingman_core.settings import GitLabSettings

sys.path.insert(0, str(Path(__file__).parent))
from service_settings import env_names, read_by_services

ROOT = Path(__file__).resolve().parents[2]
# Read by libraries, not by a settings class: httpx's CA bundle.
LIBRARY_VARIABLES = {"SSL_CERT_FILE"}
# Set by the image (docs/ops/images.md), not by the chart.
IMAGE_VARIABLES = {"WINGMAN_VERSION", "WINGMAN_COMMIT"}
# Only for WINGMAN_GIT_BACKEND=fake, which production refuses.
FAKE_ONLY = {"WINGMAN_GIT_BACKEND", "WINGMAN_FIXTURES_DIR"}
# Every optional setting the chart sets with an `if`, and the values that turn it on.
ALL_ON = ["--set", "tls.caBundle=x", "--set", "clusterStatus.enabled=true"]

HELM = shutil.which("helm")
if HELM is None:
    if os.environ.get("CI"):
        raise RuntimeError("the chart env contract needs helm on PATH in CI")
    pytest.skip("helm is not installed", allow_module_level=True)


def chart_variables(*extra: str) -> set[str]:
    assert HELM is not None
    rendered = subprocess.run(  # noqa: S603 - a fixed argv, no shell
        [HELM, "template", "wingman", str(ROOT / "chart"), "--namespace", "wingman", *extra],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    keys: set[str] = set()
    for doc in yaml.safe_load_all(rendered):
        if doc and doc.get("metadata", {}).get("name") in {"wingman-config", "wingman-secrets"}:
            keys |= set(doc.get("data") or {}) | set(doc.get("stringData") or {})
    assert keys, "the chart rendered neither wingman-config nor wingman-secrets"
    return keys


def test_every_variable_the_chart_sets_is_read_by_a_service() -> None:
    unread = chart_variables(*ALL_ON) - set(read_by_services()) - LIBRARY_VARIABLES
    assert not unread, f"the chart sets variables no settings class reads: {sorted(unread)}"


def test_every_required_setting_is_set_by_the_chart() -> None:
    required = {name for name, needed in read_by_services().items() if needed}
    missing = required - chart_variables() - IMAGE_VARIABLES - FAKE_ONLY
    assert not missing, f"required settings the chart never sets: {sorted(missing)}"


def test_the_gitlab_token_reaches_the_name_the_core_reads() -> None:
    assert "GITLAB_TOKEN" in env_names(GitLabSettings)
    assert "GITLAB_TOKEN" in chart_variables()
