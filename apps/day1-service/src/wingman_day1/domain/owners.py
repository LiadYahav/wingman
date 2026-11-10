"""The owner fields are numbers (ADR-0028).

A cluster's owner is three organisation numbers: ``owner_merkaz``,
``owner_anaf`` and ``owner_mador`` as template inputs (``owner.merkaz``,
``owner.anaf``, ``owner.mador`` in the file). Each is a string of ASCII
digits, so a leading zero survives and the template, which quotes it, writes
it as it was given. Day1 checks them at create and wherever a flavor presets
or locks one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

OWNER_INPUTS: Final = ("owner_merkaz", "owner_anaf", "owner_mador")
MAX_OWNER_DIGITS: Final = 10

_DIGITS = re.compile(rf"[0-9]{{1,{MAX_OWNER_DIGITS}}}")


def owner_problems(values: Mapping[str, object]) -> list[str]:
    """Why the owner inputs ``values`` sets are not numbers; empty when they are."""
    problems: list[str] = []
    for name in OWNER_INPUTS:
        if name not in values:
            continue
        value = values[name]
        if not isinstance(value, str) or _DIGITS.fullmatch(value) is None:
            problems.append(
                f"{name}: must be a number of 1 to {MAX_OWNER_DIGITS} digits, sent as a string "
                f'like "1234" (got {value!r})'
            )
    return problems
