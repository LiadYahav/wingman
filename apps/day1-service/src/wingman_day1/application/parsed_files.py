"""What a cluster file's text says, parsed once per distinct text (ADR-0041).

YAML parsing was most of a cluster list's time, repeated for every file on
every request; the result depends only on the text, and nothing changes it
after, so it is kept, by content, for the few hundred files of a production
repo.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Final

from wingman_day1.domain.cluster_file import (
    ClusterValues,
    Provenance,
    load_values,
    read_provenance,
    read_values,
)
from wingman_day1.domain.errors import InvalidClusterFileError

MAX_PARSED: Final = 4096
"""Parsed cluster files kept, by content; a production repo has a few hundred."""


@dataclass(frozen=True, slots=True)
class ParsedFile:
    """A cluster file's values (``None`` when it does not parse), header and problems."""

    values: ClusterValues | None
    provenance: Provenance
    problems: tuple[str, ...]


class ParsedFiles:
    """The newest ``MAX_PARSED`` distinct texts, parsed."""

    def __init__(self) -> None:
        """Start empty."""
        self._parsed: OrderedDict[str, ParsedFile] = OrderedDict()

    def parse(self, content: str) -> ParsedFile:
        """The file's values, header and problems; never raises."""
        hit = self._parsed.get(content)
        if hit is not None:
            self._parsed.move_to_end(content)
            return hit
        problems: list[str] = []
        values: ClusterValues | None = None
        try:
            values = read_values(load_values(content))
        except InvalidClusterFileError as exc:
            problems.extend(exc.problems or [str(exc)])
        provenance = read_provenance(content)
        problems.extend(provenance.problems)
        hit = ParsedFile(values, provenance, tuple(problems))
        self._parsed[content] = hit
        if len(self._parsed) > MAX_PARSED:
            self._parsed.popitem(last=False)
        return hit
