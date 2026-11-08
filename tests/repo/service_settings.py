"""What the services read from the environment, for the repository contracts.

Shared by ``test_chart_env_contract.py`` (the chart sets exactly these) and
``test_web_docs_contract.py`` (the docs name only these). Not a test module:
the tests run with ``--import-mode=importlib``, so each puts this directory on
``sys.path`` before importing it.
"""

from __future__ import annotations

from pydantic import AliasChoices
from pydantic_settings import BaseSettings

from wingman_core.settings import AuthSettings, GitLabSettings, RuntimeSettings
from wingman_day1.settings import Day1Settings
from wingman_day2.settings import Day2Settings

SETTINGS: tuple[type[BaseSettings], ...] = (
    GitLabSettings,
    AuthSettings,
    RuntimeSettings,
    Day1Settings,
    Day2Settings,
)
"""Every settings class day1 and day2 load (ADR-0009)."""


def env_names(cls: type[BaseSettings]) -> dict[str, bool]:
    """Every environment name ``cls`` reads, aliases included, and whether it is required."""
    prefix = str(cls.model_config.get("env_prefix", "")).upper()
    names: dict[str, bool] = {}
    for field_name, field in cls.model_fields.items():
        alias = field.validation_alias
        choices = alias.choices if isinstance(alias, AliasChoices) else [alias or field_name]
        for choice in choices:
            if isinstance(choice, str):
                names[(choice if alias else prefix + choice).upper()] = field.is_required()
    return names


def read_by_services() -> dict[str, bool]:
    """Every environment name any settings class reads, and whether it is required."""
    names: dict[str, bool] = {}
    for cls in SETTINGS:
        names.update(env_names(cls))
    return names
