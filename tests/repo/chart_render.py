"""``helm template`` of the chart, for the chart tests.

Every render sets the Wingman image tags unless asked not to: the chart has
no default tag and refuses to render without one (ADR-0059), as
``ci/default-values.yaml`` shows.
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
HELM = shutil.which("helm")


def require_helm(what: str) -> None:
    """Skip the calling test module without helm, except in CI, where it must be there."""
    if HELM is None:
        if os.environ.get("CI"):
            raise RuntimeError(f"{what} need helm on PATH in CI")
        pytest.skip("helm is not installed", allow_module_level=True)


def template(*extra: str, tags: bool = True) -> subprocess.CompletedProcess[str]:
    """The chart rendered with ``extra``; a refused render is returned, not raised."""
    assert HELM is not None
    argv = [HELM, "template", "wingman", str(CHART), "--namespace", "wingman"]
    return subprocess.run(  # noqa: S603 - a fixed argv, no shell
        [*argv, *(TAGS if tags else ()), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def render(*extra: str) -> list[dict[str, Any]]:
    """Every rendered document; the render must succeed."""
    result = template(*extra)
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]
