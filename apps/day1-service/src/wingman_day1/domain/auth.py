"""Who logs in, as OpenShift reports them, before Wingman gives them a role."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Identity:
    """An OpenShift user (``GET /apis/user.openshift.io/v1/users/~``)."""

    username: str
    groups: tuple[str, ...] = ()
    uid: str = ""
    full_name: str = ""
