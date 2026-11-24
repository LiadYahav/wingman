"""A response as a viewer reads it: admin-only fields null, texts redacted (ADR-0068)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel

from wingman_core.domain.redaction import HIDDEN, Redactor
from wingman_core.web.viewer import ADMIN_ONLY, all_for_viewer, for_viewer

MCE = "ocp4-prod-mce-site1-a"
REDACTOR = Redactor.of([MCE])


class Phase(StrEnum):
    READY = "Ready"


class Inner(BaseModel):
    mce: Annotated[str | None, ADMIN_ONLY]
    words: str


class Outer(BaseModel):
    name: str
    path: Annotated[str | None, ADMIN_ONLY] = None
    phase: Phase
    inner: Inner
    lines: list[str]
    pair: tuple[str, int]
    versions: dict[str, str]
    count: int


def _outer() -> Outer:
    return Outer(
        name="ocp4-prod-lark-site1",
        path=f"sites/site1/mces/{MCE}/hostedClusters/ocp4-prod-lark-site1.yaml",
        phase=Phase.READY,
        inner=Inner(mce=MCE, words=f"waiting for {MCE}"),
        lines=[f"read {MCE}", "fine"],
        pair=(f"on {MCE}", 2),
        versions={MCE: f"{MCE} 2.8"},
        count=3,
    )


def test_admin_only_fields_are_null_at_any_depth() -> None:
    shown = for_viewer(_outer(), REDACTOR)
    assert shown.path is None
    assert shown.inner.mce is None


def test_every_other_text_is_redacted_and_the_rest_kept() -> None:
    shown = for_viewer(_outer(), REDACTOR)
    assert shown.name == "ocp4-prod-lark-site1"
    assert shown.inner.words == f"waiting for {HIDDEN}"
    assert shown.lines == [f"read {HIDDEN}", "fine"]
    assert shown.pair == (f"on {HIDDEN}", 2)
    assert shown.versions == {HIDDEN: f"{HIDDEN} 2.8"}
    assert (shown.phase, shown.count) == (Phase.READY, 3)
    assert MCE not in shown.model_dump_json()


def test_the_original_is_left_as_it_was() -> None:
    outer = _outer()
    all_for_viewer([outer], REDACTOR)
    assert outer.inner.mce == MCE
