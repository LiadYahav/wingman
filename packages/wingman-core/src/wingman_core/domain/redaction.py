"""The infrastructure names Wingman knows, out of the free text a viewer reads (ADR-0068).

A viewer is a customer (ADR-0067): they never learn the name of an MCE, a
seed, a KV cluster, a hub or a UPI cluster. A response's structured fields
that hold one are an admin's and a viewer's answer leaves them ``null``; free
text is not parsed (a merge request's title and description, a commit's
message, a workflow's words, a condition's message), but every name the
service knows is replaced by :data:`HIDDEN` before a viewer reads it. A name
the service does not know, a server's or an address, is not found: the rule
is the names, not a guess at what a sentence means.

A name matches as a whole token: the characters a name is made of (letters,
digits and ``-``) on either side end the match, so
``ocp4-prod-mce-site1-a`` is found in ``api.ocp4-prod-mce-site1-a.lab:6443``
and in ``sites/site1/mces/ocp4-prod-mce-site1-a/``, never inside a longer
name. Case is ignored: a Kubernetes name is lowercase, the text may not be.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

HIDDEN: Final = "[hidden]"
"""What a viewer reads where an infrastructure name was."""

_NAME_CHARS: Final = "A-Za-z0-9-"


@dataclass(frozen=True, slots=True)
class Redactor:
    """Replaces each of ``names`` in a text by :data:`HIDDEN`; with none, changes nothing."""

    names: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def of(cls, names: Iterable[str]) -> Redactor:
        """From any names; empty ones are dropped."""
        return cls(frozenset(name for name in names if name))

    def __or__(self, other: Redactor) -> Redactor:
        """Both redactors' names."""
        return Redactor(self.names | other.names)

    def text(self, value: str) -> str:
        """``value`` with every name replaced; the same string when none is in it."""
        pattern = _pattern(self.names)
        return value if pattern is None else pattern.sub(HIDDEN, value)


@functools.lru_cache(maxsize=16)
def _pattern(names: frozenset[str]) -> re.Pattern[str] | None:
    """One alternation, longest name first, so a name that starts another never cuts it."""
    if not names:
        return None
    alternatives = "|".join(re.escape(n) for n in sorted(names, key=lambda n: (-len(n), n)))
    return re.compile(rf"(?<![{_NAME_CHARS}])(?:{alternatives})(?![{_NAME_CHARS}])", re.IGNORECASE)


NO_REDACTION: Final = Redactor()
"""An admin's: every text as it is."""
