"""The body of ``GET /api/day1/machine-configs``: the catalogue and the nodepool defaults."""

from __future__ import annotations

from pydantic import BaseModel

from wingman_day1.application.machine_configs import MachineConfigOverview
from wingman_day1.domain.machine_configs import NETWORK_CONFIG
from wingman_day1.domain.paths import NODEPOOL_DEFAULTS_FILE


class StaticConfigOut(BaseModel):
    """A static config a nodepool may name: ``{name: <name>}``."""

    name: str
    folder: str
    """Its folder under ``mc-files/``; ``""`` for the root."""
    path: str


class HardwareTypeOut(BaseModel):
    """A hardware type for ``{name: nm-conf, hardware: <name>}``."""

    name: str
    template: str
    generic: bool
    """``generic``: ``nm-conf-template.bu``, for any hardware, written as plain ``nm-conf``."""


class NodepoolDefaultsOut(BaseModel):
    """``nodepool-defaults.yaml``: the entries a new nodepool starts with."""

    path: str
    found: bool
    """``false``: the specs project has no such file, so there are no defaults."""
    configs: list[dict[str, str]]
    """Entries in the template-input shape; ``hardware`` is absent when the nodepool picks it."""
    error: str | None
    """Set when the file exists but cannot be used; ``configs`` is then empty."""
    problems: list[str]
    """With ``error``: why. Without: the entries that would not resolve."""


class MachineConfigsOut(BaseModel):
    """``GET /api/day1/machine-configs``: the catalogue and the nodepool defaults."""

    network_config: str
    static_configs: list[StaticConfigOut]
    hardware_types: list[HardwareTypeOut]
    nodepool_defaults: NodepoolDefaultsOut
    problems: list[str]
    """Files in ``mc-files/`` that are not offered, and why."""

    @classmethod
    def of(cls, overview: MachineConfigOverview) -> MachineConfigsOut:
        """From the overview."""
        catalog, reading = overview.catalog, overview.defaults
        error = reading.error
        return cls(
            network_config=NETWORK_CONFIG,
            static_configs=[
                StaticConfigOut(name=c.name, folder=c.folder, path=str(c.path))
                for c in catalog.static_configs()
            ],
            hardware_types=[
                HardwareTypeOut(name=h.name, template=str(h.template), generic=h.generic)
                for h in catalog.hardware_types()
            ],
            nodepool_defaults=NodepoolDefaultsOut(
                path=str(NODEPOOL_DEFAULTS_FILE),
                found=reading.found,
                configs=[e.to_input() for e in reading.defaults.configs],
                error=str(error) if error else None,
                problems=list(error.problems) if error else list(overview.defaults_problems),
            ),
            problems=list(catalog.problems),
        )
