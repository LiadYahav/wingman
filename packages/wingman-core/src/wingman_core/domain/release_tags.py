"""An OpenShift release tag, as a cluster file's ``mastertag`` writes it.

A release image's tag is the release, then the architecture it is built for:
``4.16.27-x86_64``, ``4.16.0-rc.1-aarch64``, ``4.21.40-multi``. The
hostedclusters-setup chart (``hc.releaseTag`` in team-redbull's
helm-charts-hostedclusters-setup) adds ``-x86_64`` to a bare ``X.Y.Z`` and
uses any other tag as written, as the release image's tag. Two rules follow:

- :func:`without_arch` is the release a tag names. A last part that is one of
  :data:`ARCHES` comes off; a prerelease stays (``4.16.0-rc.1-x86_64`` is
  ``4.16.0-rc.1``), and so does a suffix that is no architecture. The upgrade
  ladder writes releases this way.
- :func:`is_release_tag` is a tag the chart can render into a release image
  OpenShift publishes: ``X.Y.Z``, then optionally ``-`` and more of what such
  a tag holds (lower-case letters, digits, ``_``, ``.``, ``-``), at most 128
  characters in all, as an image tag may be.

Not day2's OCP version: the day2 platform keys its version pins by what comes
before the first ``-`` (``wingman_day2.domain.versions.ocp_version``), so
there a prerelease counts as its ``X.Y.Z``. That is the platform's own rule.

The web has the same release rule in ``apps/web/lib/release-tags.ts``.
"""

from __future__ import annotations

import re
from typing import Final

ARCHES: Final = ("x86_64", "aarch64", "ppc64le", "s390x", "multi")
"""The architectures OpenShift publishes release images for, as a tag's last part."""
MAX_TAG_LENGTH: Final = 128
"""The longest image tag a registry takes (the OCI distribution spec)."""

_TAG: Final = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9_.-]+)?")


def without_arch(tag: str) -> str:
    """The release ``tag`` names: ``4.16.0-rc.1-x86_64`` → ``4.16.0-rc.1``; other tags as given."""
    release, dash, arch = tag.rpartition("-")
    return release if dash and arch in ARCHES else tag


def is_release_tag(tag: str) -> bool:
    """Whether ``tag`` has the shape of an OpenShift release tag the chart can render."""
    return len(tag) <= MAX_TAG_LENGTH and _TAG.fullmatch(tag) is not None
