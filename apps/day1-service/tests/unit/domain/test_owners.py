"""Owner fields are numbers (ADR-0028)."""

from __future__ import annotations

import pytest

from wingman_day1.domain.owners import OWNER_INPUTS, owner_problems


@pytest.mark.parametrize("value", ["0", "7", "56", "1234", "0042", "9" * 10])
def test_a_string_of_one_to_ten_digits_is_an_owner(value: str) -> None:
    assert owner_problems(dict.fromkeys(OWNER_INPUTS, value)) == []


@pytest.mark.parametrize(
    "value",
    [
        "",
        " 12",
        "12 ",
        "12\n",
        "1a",
        "-1",
        "1.5",
        "1e3",
        "9" * 11,
        chr(0x661) + chr(0x662),  # Arabic-Indic digits: \d matches them, owners are ASCII
        chr(0xFF11) + chr(0xFF12),  # full-width digits
        1234,
        1.0,
        True,
        None,
    ],
)
def test_anything_else_is_refused(value: object) -> None:
    assert owner_problems({"owner_anaf": value}) == [
        'owner_anaf: must be a number of 1 to 10 digits, sent as a string like "1234" '
        f"(got {value!r})"
    ]


def test_every_bad_owner_is_listed_and_absent_ones_are_not_checked() -> None:
    problems = owner_problems({"owner_merkaz": "x", "owner_mador": "", "platform": "kubevirt"})
    assert [p.split(":")[0] for p in problems] == ["owner_merkaz", "owner_mador"]
    assert owner_problems({}) == []
