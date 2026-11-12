"""Fake Quick Links checks and ArgoCD counts (ADR-0052).

Tests seed them directly; ``DAY1_FAKE_FLEET=true`` (development only) seeds
them from ``dev/fleet-fixtures/quick-links.yaml``, and shows the demo links
file ``dev/fleet-fixtures/quick-links-links.yaml`` when ``QUICK_LINKS_FILE``
does not exist, so the page demos without a network.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

from wingman_core.ports.clock import Clock, system_clock
from wingman_day1.domain.quick_links import (
    AppCounts,
    ArgoCdReading,
    HealthCounts,
    LinkReading,
    LinkState,
    SyncCounts,
)

CHECKS_FILE: Final = Path("dev/fleet-fixtures/quick-links.yaml")
DEMO_LINKS_FILE: Final = Path("dev/fleet-fixtures/quick-links-links.yaml")


@dataclass(frozen=True, slots=True)
class CheckRule:
    """What a check of a URL containing ``match`` answers (``""`` matches every URL)."""

    match: str
    state: LinkState = LinkState.UP
    reason: str = "answered 200"
    http_status: int | None = 200
    latency_ms: int | None = 40


UP: Final = CheckRule("")


class FakeLinkProbe:
    """A ``LinkProbe`` answering from rules: the first whose ``match`` is in the URL wins."""

    def __init__(
        self,
        rules: Iterable[CheckRule] = (),
        *,
        default: CheckRule = UP,
        clock: Clock = system_clock,
    ) -> None:
        """Answer from ``rules``, else ``default``."""
        self._rules = tuple(rules)
        self._default = default
        self._clock = clock
        self.checked: list[str] = []
        """Every URL checked, in order."""

    async def check(self, url: str) -> LinkReading:
        """See LinkProbe.check."""
        self.checked.append(url)
        rule = next((r for r in self._rules if r.match in url), self._default)
        return LinkReading(
            url,
            rule.state,
            rule.reason,
            self._clock(),
            http_status=rule.http_status,
            latency_ms=rule.latency_ms,
        )


class FakeArgoCd:
    """An ``ArgoCdApi`` with a token for each seeded instance: its counts, or an error."""

    def __init__(
        self, answers: Mapping[str, AppCounts | str], *, clock: Clock = system_clock
    ) -> None:
        """``answers`` maps an instance to its counts, or to the error its read fails with."""
        self._answers = dict(answers)
        self._clock = clock
        self.reads: list[tuple[str, str]] = []
        """Every ``(instance, url)`` read, in order."""

    def has_token(self, instance: str) -> bool:
        """See ArgoCdApi.has_token."""
        return instance in self._answers

    async def application_counts(self, instance: str, url: str) -> ArgoCdReading:
        """See ArgoCdApi.application_counts."""
        self.reads.append((instance, url))
        answer = self._answers.get(instance, "no token is configured")
        if isinstance(answer, str):
            return ArgoCdReading(instance, self._clock(), error=answer)
        return ArgoCdReading(instance, self._clock(), counts=answer)


def counts(
    *,
    synced: int = 0,
    out_of_sync: int = 0,
    healthy: int = 0,
    progressing: int = 0,
    degraded: int = 0,
    missing: int = 0,
    suspended: int = 0,
) -> AppCounts:
    """Counts of ``synced + out_of_sync`` applications; health they do not add up to is unknown."""
    total = synced + out_of_sync
    known = healthy + progressing + degraded + missing + suspended
    return AppCounts(
        total,
        SyncCounts(synced=synced, out_of_sync=out_of_sync),
        HealthCounts(
            healthy=healthy,
            progressing=progressing,
            degraded=degraded,
            missing=missing,
            suspended=suspended,
            unknown=max(0, total - known),
        ),
    )


def fleet_fixture(relative: Path) -> Path:
    """``relative`` (under ``dev/fleet-fixtures``) of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / relative
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{relative} not found above this file")


def load_fake_quick_links(
    path: Path, *, clock: Clock = system_clock
) -> tuple[FakeLinkProbe, FakeArgoCd]:
    """The fake probe and ArgoCD of a fixture (``checks`` rules, ``argocd`` answers)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"{path}: expected a mapping with 'checks' and 'argocd'")
    rules = [
        CheckRule(
            match=str(rule["match"]),
            state=LinkState(rule.get("state", "up")),
            reason=str(rule.get("reason", "answered 200")),
            http_status=rule.get("http_status"),
            latency_ms=rule.get("latency_ms"),
        )
        for rule in raw.get("checks") or []
    ]
    answers: dict[str, AppCounts | str] = {}
    for instance, answer in (raw.get("argocd") or {}).items():
        if not isinstance(answer, dict):
            raise TypeError(f"{path}: argocd.{instance} must be a mapping")
        answers[str(instance)] = (
            str(answer["error"])
            if "error" in answer
            else counts(**{k: int(v) for k, v in answer.items()})
        )
    return FakeLinkProbe(rules, clock=clock), FakeArgoCd(answers, clock=clock)
