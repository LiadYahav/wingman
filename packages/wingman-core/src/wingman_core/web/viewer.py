"""A response as a viewer reads it: no admin's field, no infrastructure name (ADR-0068).

A response model marks each field that names the infrastructure (an MCE, a
path through it, a link to it) with :data:`ADMIN_ONLY` in its annotation::

    mce: Annotated[str | None, ADMIN_ONLY]

:func:`for_viewer` answers the model with every such field ``None``, at any
depth, and every other text passed through the service's
:class:`~wingman_core.domain.redaction.Redactor`: the names it knows become
``[hidden]`` in titles, messages, diffs and a workflow's words. An admin's
answer never goes through it.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from pydantic import BaseModel

from wingman_core.domain.redaction import Redactor


class AdminOnly:
    """Field metadata: the field is ``None`` in a viewer's answer, so its type must allow it."""

    __slots__ = ()

    def __repr__(self) -> str:
        """Its name in an annotation's repr."""
        return "ADMIN_ONLY"


ADMIN_ONLY: Final = AdminOnly()


def for_viewer[M: BaseModel](model: M, redactor: Redactor) -> M:
    """``model`` with its admin-only fields ``None`` and its texts redacted, nested models too."""
    updates = {
        name: None
        if any(isinstance(m, AdminOnly) for m in info.metadata)
        else _shown(getattr(model, name), redactor)
        for name, info in type(model).model_fields.items()
    }
    return model.model_copy(update=updates)


def all_for_viewer[M: BaseModel](models: list[M], redactor: Redactor) -> list[M]:
    """:func:`for_viewer` of each."""
    return [for_viewer(m, redactor) for m in models]


def _shown(value: object, redactor: Redactor) -> object:
    match value:
        case Enum():
            return value
        case str():
            return redactor.text(value)
        case BaseModel():
            return for_viewer(value, redactor)
        case list():
            return [_shown(v, redactor) for v in value]
        case tuple():
            return tuple(_shown(v, redactor) for v in value)
        case dict():
            return {_shown(k, redactor): _shown(v, redactor) for k, v in value.items()}
        case _:
            return value
