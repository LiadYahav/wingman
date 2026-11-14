"""Where a team's chart repos sit (ADR-0060)."""

from __future__ import annotations

from wingman_day2.domain.teams import charts_group


def test_a_teams_charts_sit_in_its_own_helm_charts_group() -> None:
    assert charts_group("orca") == "orca/helm-charts"
    assert charts_group("redbull") == "redbull/helm-charts"
