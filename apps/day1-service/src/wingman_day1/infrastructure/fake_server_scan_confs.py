"""The fake fleet's hardware catalog: the Confs page with ``DAY1_FAKE_FLEET=true`` (ADR-0048).

``dev/fleet-fixtures/confs.yaml`` holds server-scan's own fake catalog in
the shape of its ``GET /api/v1/confs`` answer, read by the same strict model
as the real answer (through JSON, as the HTTP adapter reads it), so the
fixture cannot drift from the shape. Nothing here is real.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import yaml

from wingman_day1.domain.server_scan_confs import ConfList
from wingman_day1.infrastructure.fake_fleet import default_fleet_file

CONFS_FILE_NAME: Final = "confs.yaml"


def default_confs_file() -> Path:
    """``dev/fleet-fixtures/confs.yaml`` of this checkout, beside the fleet's servers."""
    return default_fleet_file().with_name(CONFS_FILE_NAME)


def load_confs(path: Path) -> ConfList:
    """The catalog of a fixture in server-scan's answer shape; a malformed one raises."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ConfList.model_validate_json(json.dumps(raw))
