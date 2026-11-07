"""``defaults/<scope>/exclusions.yaml``: the one structural opt-out from a fleet default.

``exclusions: {<chart>: [<MCE or cluster name>, ...]}``. The operators chart
turns it into ``exclude:`` entries of the defaults generator. The template is
strict about types (a non-map ``exclusions`` or a non-list entry makes it
``fail``, so no app of that scope renders for the team) and silent about
names (a typo excludes nothing); ``lints.lint_exclusions`` catches both.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

EXCLUSIONS_KEY: Final = "exclusions"


@dataclass(frozen=True, slots=True)
class Exclusions:
    """Which names each fleet-default chart is excluded from."""

    by_chart: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def excluded_charts(self, name: str) -> frozenset[str]:
        """The charts whose list names ``name``."""
        return frozenset(chart for chart, names in self.by_chart.items() if name in names)


def platform_exclusions(doc: object) -> Exclusions | None:
    """What the operators chart makes of an exclusions file; ``None`` where its render fails.

    ``doc`` is the parsed file (``None`` when absent or empty). A file Helm
    cannot load as values (not a mapping) fails the render too. Only
    ``exclusions`` is read, as ``.Values.exclusions | default dict``.
    """
    if doc is not None and not isinstance(doc, Mapping):
        return None
    raw = doc.get(EXCLUSIONS_KEY) if isinstance(doc, Mapping) else None
    if not raw:
        return Exclusions()
    if not isinstance(raw, Mapping):
        return None
    by_chart: dict[str, tuple[str, ...]] = {}
    for chart, names in raw.items():
        if not names:
            continue
        if not isinstance(names, list):
            return None
        by_chart[str(chart)] = tuple(str(n) for n in names)
    return Exclusions(by_chart)
