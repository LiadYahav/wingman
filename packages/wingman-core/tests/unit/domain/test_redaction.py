"""Infrastructure names out of a viewer's free text, as whole tokens (ADR-0068)."""

from __future__ import annotations

import pytest

from wingman_core.domain.redaction import HIDDEN, NO_REDACTION, Redactor

MCE = "ocp4-prod-mce-site1-a"
SEED = "ocp4-prod-seed-site1-az1-a"
KV = "ocp4-prod-kv-site1-az1-a"
REDACTOR = Redactor.of([MCE, SEED, KV, ""])


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        (
            f"Deleting hosted cluster x (site `site1`, MCE `{MCE}`).",
            f"(site `site1`, MCE `{HIDDEN}`)",
        ),
        (f"sites/site1/mces/{MCE}/hostedClusters/x.yaml", f"mces/{HIDDEN}/hostedClusters"),
        (f"GET https://api.{MCE}.lab.example:6443/apis", f"https://api.{HIDDEN}.lab"),
        (f"Modify cluster {KV} via Wingman", f"Modify cluster {HIDDEN} via"),
        (f"on seed {SEED.upper()}", f"on seed {HIDDEN}"),
    ],
)
def test_a_known_name_is_hidden_wherever_it_stands(text: str, shown: str) -> None:
    assert shown in REDACTOR.text(text)
    assert MCE not in REDACTOR.text(text).lower()


@pytest.mark.parametrize(
    "text",
    [
        f"{MCE}-agents",  # a longer name that starts with an MCE's is another name
        f"hcp-{KV}",
        "ocp4-prod-lark-site1 on site1",
    ],
)
def test_a_name_inside_a_longer_name_is_left_alone(text: str) -> None:
    assert REDACTOR.text(text) == text


def test_the_longest_name_wins_when_one_starts_another() -> None:
    redactor = Redactor.of(["ocp4-prod-mce-site1", "ocp4-prod-mce-site1-a"])
    assert redactor.text("on ocp4-prod-mce-site1-a now") == f"on {HIDDEN} now"


def test_without_names_nothing_changes() -> None:
    assert NO_REDACTION.text(f"on {MCE}") == f"on {MCE}"
    assert Redactor.of([""]).names == frozenset()


def test_two_redactors_hide_both_names() -> None:
    both = Redactor.of([MCE]) | Redactor.of([KV])
    assert both.text(f"{MCE} {KV}") == f"{HIDDEN} {HIDDEN}"
