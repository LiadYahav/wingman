"""The clusters list's "Upgrade available → <version>" (ADR-0055's 3.20.0 amendment).

The newest release the cluster's MCE offers a new cluster (ADR-0034) above
its mastertag. A suggestion only: the workflow plans the path, so the hint
is the newest offered release, never a next step.
"""

from __future__ import annotations

import pytest

from wingman_day1.domain.openshift_versions import OpenShiftVersions, upgrade_hint

PROD = OpenShiftVersions("ocp4-prod-mce-site1-a", ("4.18.56", "4.17.58", "4.16.55"))


@pytest.mark.parametrize("mastertag", ["4.18.22-x86_64", "4.18.22", " 4.18.22-x86_64 "])
def test_the_newest_offered_release_above_the_mastertag(mastertag: str) -> None:
    assert upgrade_hint(mastertag, PROD) == "4.18.56"


def test_the_newest_not_the_next_step_the_workflow_plans_the_path() -> None:
    assert upgrade_hint("4.16.27-x86_64", PROD) == "4.18.56"


def test_releases_compare_as_numbers_not_text() -> None:
    assert upgrade_hint("4.18.9", OpenShiftVersions("m", ("4.18.10",))) == "4.18.10"
    assert upgrade_hint("4.18.10", OpenShiftVersions("m", ("4.18.9",))) is None


def test_the_order_offered_does_not_matter() -> None:
    assert upgrade_hint("4.16.27", OpenShiftVersions("m", ("4.16.55", "4.18.56", "4.17.58"))) == (
        "4.18.56"
    )


@pytest.mark.parametrize(
    "mastertag",
    [
        "4.18.56-x86_64",  # at the newest offered
        "4.19.10-x86_64",  # ahead of every minor the MCE hosts
    ],
)
def test_up_to_date_or_ahead_has_no_hint(mastertag: str) -> None:
    assert upgrade_hint(mastertag, PROD) is None


@pytest.mark.parametrize("mastertag", [None, "", "latest", "4.18", "v4.18.22", "4.18.22-arm64"])
def test_no_mastertag_or_not_a_release_has_no_hint(mastertag: str | None) -> None:
    assert upgrade_hint(mastertag, PROD) is None


def test_an_mce_that_offers_nothing_has_no_hint() -> None:
    offered = OpenShiftVersions("m", (), ("MCE m has no upgrade/mces/m.yaml ...",))
    assert upgrade_hint("4.16.27-x86_64", offered) is None
