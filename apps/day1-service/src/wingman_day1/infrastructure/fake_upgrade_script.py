"""The upgrade fake's fixture, ``dev/fleet-fixtures/upgrade.yaml`` (ADR-0055).

Targets by cluster, in the orchestrator's own shape and read with the real
parser (``default`` for a cluster not listed), and the steps a fake run
walks: phases and texts as data, never a list in code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

from wingman_day1.domain.upgrades import UpgradeDecision, UpgradeTargets
from wingman_day1.infrastructure.upgrade_payloads import upgrade_targets

UPGRADE_FILE: Final = Path("dev/fleet-fixtures/upgrade.yaml")
SECTIONS: Final = ("before", "control_plane", "each_nodepool", "after")
"""``control_plane`` runs once, ``each_nodepool`` once per NodePool of the plan."""


@dataclass(frozen=True, slots=True)
class ScriptStep:
    """One step of the fixture's run: its phase, its text, and what moves it on."""

    phase: str
    waiting_for: str = ""
    seconds: float = 0.0
    waits_for: UpgradeDecision | None = None
    moves: str | None = None
    """``control-plane`` or ``nodepool``: that version is the target's once the step is over."""


@dataclass(frozen=True, slots=True)
class UpgradeScript:
    """The fixture: targets by cluster (``default`` for the rest) and the run's steps."""

    targets: Mapping[str, UpgradeTargets]
    steps: Mapping[str, tuple[ScriptStep, ...]]


def default_upgrade_file() -> Path:
    """``dev/fleet-fixtures/upgrade.yaml`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / UPGRADE_FILE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{UPGRADE_FILE} not found above this file")


def load_upgrade_script(path: Path) -> UpgradeScript:
    """The fixture's targets (the orchestrator's shape) and run steps."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("targets"), dict):
        raise TypeError(f"{path}: expected a mapping with 'targets' and 'run'")
    targets = {
        str(name): upgrade_targets({"cluster": str(name), **body})
        for name, body in raw["targets"].items()
    }
    run = raw.get("run")
    if not isinstance(run, dict) or set(run) - set(SECTIONS):
        raise TypeError(f"{path}: 'run' has the sections {', '.join(SECTIONS)}")
    steps = {name: tuple(_script_step(item) for item in run.get(name) or ()) for name in SECTIONS}
    return UpgradeScript(targets=targets, steps=steps)


def _script_step(raw: object) -> ScriptStep:
    if not isinstance(raw, dict) or not isinstance(raw.get("phase"), str):
        raise TypeError(f"a run step needs a phase: {raw!r}")
    waits, moves = raw.get("waits_for"), raw.get("moves")
    return ScriptStep(
        phase=raw["phase"],
        waiting_for=str(raw.get("waiting_for") or ""),
        seconds=float(raw.get("seconds") or 0),
        waits_for=UpgradeDecision(str(waits)) if waits else None,
        moves=str(moves) if moves else None,
    )
