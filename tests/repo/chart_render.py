"""``helm template`` of the chart, for the chart tests.

Every render sets what the chart requires unless asked not to, as
``ci/default-values.yaml`` does: the Wingman image tags (there is no default
tag, ADR-0059) and the workflows orchestrator every create starts
provision-cluster on (ADR-0042), with the server-scan its uninstall needs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy/helm/wingman"
TAG = "3.33.0"
TAGS = tuple(
    arg for name in ("day1", "day2", "web") for arg in ("--set", f"image.{name}.tag={TAG}")
)
ORCHESTRATOR = "http://workflows-orchestrator-api.ns.svc:8080"
SERVER_SCAN = "http://server-scan-api.ns.svc:8000"
REQUIRED = (
    *TAGS,
    *("--set", f"workflows.url={ORCHESTRATOR}", "--set", f"serverScan.url={SERVER_SCAN}"),
)
"""The values the chart refuses to render without (outside ``environment: development``)."""
HELM = shutil.which("helm")


def require_helm(what: str) -> None:
    """Skip the calling test module without helm, except in CI, where it must be there."""
    if HELM is None:
        if os.environ.get("CI"):
            raise RuntimeError(f"{what} need helm on PATH in CI")
        pytest.skip("helm is not installed", allow_module_level=True)


def template(*extra: str, tags: bool = True) -> subprocess.CompletedProcess[str]:
    """The chart rendered with ``extra`` (and ``REQUIRED`` unless ``tags`` is false).

    A refused render is returned, not raised.
    """
    assert HELM is not None
    argv = [HELM, "template", "wingman", str(CHART), "--namespace", "wingman"]
    return subprocess.run(  # noqa: S603 - a fixed argv, no shell
        [*argv, *(REQUIRED if tags else ()), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def render(*extra: str) -> list[dict[str, Any]]:
    """Every rendered document; the render must succeed."""
    result = template(*extra)
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]
