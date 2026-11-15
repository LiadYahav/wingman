"""The routers of what a nodepool may name: machine configs (ADR-0027), tuning profiles (ADR-0061).

Both read a folder of the day1 repo; ``main`` mounts them as one entry, so
another nodepool catalogue adds its router here, not to the composition root.
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter

from wingman_day1.api.v1 import machine_configs, tuning_profiles

ROUTERS: Final[tuple[APIRouter, ...]] = (machine_configs.router, tuning_profiles.router)
