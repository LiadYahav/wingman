"""The MCE tokens file (``MCE_TOKENS_FILE``): each MCE hub's token, and its own address.

The legacy ``{<mce>: <token>}``, or ``{<mce>: {token: <token>, url:
https://<host>[:<port>]}}`` for a hub whose address is not the convention's
``https://api.<mce>.<domain>:6443`` (ADR-0045). ``HttpHubApi`` takes what
this reads. A token never appears in an error: messages name the MCE key.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import yaml


@dataclass(frozen=True, slots=True)
class MceAccess:
    """What the tokens file says: each MCE's token, and the hubs with their own address."""

    tokens: Mapping[str, str]
    urls: Mapping[str, str] = field(default_factory=dict)
    """``https://<host>[:<port>]`` per MCE that sets one; the others use the convention."""


def load_mce_access(path: Path) -> MceAccess:
    """Read the tokens file: per MCE, a token, or a mapping with ``token`` and ``url``.

    Raises ``ValueError`` (naming the MCE key, never the token) for anything
    else: a key that is not an MCE name, an empty or multi-line token, an
    unknown key, or a ``url`` that is not ``https://<host>[:<port>]``. An
    empty file means no MCE is configured.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return MceAccess({})
    if not isinstance(raw, dict):
        raise ValueError(  # noqa: TRY004 - a bad settings file is one ValueError to start-up
            f"{path} must be a YAML mapping of MCE name to token"
        )
    tokens: dict[str, str] = {}
    urls: dict[str, str] = {}
    for mce, entry in raw.items():
        if not isinstance(mce, str) or not mce.strip():
            raise ValueError(f"{path}: every key must be an MCE name")
        token = entry
        if isinstance(entry, dict):
            unknown = sorted(str(key) for key in entry if key not in ("token", "url"))
            if unknown:
                raise ValueError(f"{path}: MCE {mce!r} has unknown keys {unknown}; use token, url")
            token = entry.get("token")
            if entry.get("url") is not None:
                urls[mce] = hub_url(entry["url"], what=f"{path}: the url of MCE {mce!r}")
        tokens[mce] = _token(token, what=f"{path}: the token for MCE {mce!r}")
    return MceAccess(tokens, urls)


def _token(value: object, *, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} is empty or not a string")
    if "\r" in value or "\n" in value.strip():
        raise ValueError(f"{what} spans more than one line")
    return value.strip()


def hub_url(value: object, *, what: str) -> str:
    """``https://<host>[:<port>]``, without a trailing slash; ``ValueError`` for anything else.

    A path, a query, a fragment or credentials in the URL would change what
    every read asks for, and a plain ``http://`` hub would receive the token
    in the clear.
    """
    if not isinstance(value, str):
        raise ValueError(f"{what} is not a string")  # noqa: TRY004 - one ValueError to start-up
    text = value.strip().rstrip("/")
    parts = urlsplit(text)
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"{what} has a port that is not a number") from exc
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.path
        or parts.query
        or parts.fragment
        or parts.username is not None
        or parts.password is not None
        or (port is not None and not 0 < port < 65536)
    ):
        raise ValueError(f"{what} must be https://<host>[:<port>], with nothing after it")
    return text
