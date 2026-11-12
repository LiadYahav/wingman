"""FileLinksSource: the team's links file, read from disk on every page load (ADR-0052).

The chart renders it into the ConfigMap ``wingman-quick-links``, mounted as
a directory (never ``subPath``, which the kubelet does not update), so an
edit reaches a running day1 within the kubelet's sync and needs no restart.
The file is small: reading it per request costs less than caching it would.
"""

from __future__ import annotations

from pathlib import Path

from wingman_day1.domain.quick_links import LinksFileUnreadableError


class FileLinksSource:
    """A ``LinksFileSource`` over one file."""

    def __init__(self, path: Path) -> None:
        """Read ``path``; it need not exist."""
        self._path = path

    @property
    def path(self) -> str:
        """See LinksFileSource.path."""
        return str(self._path)

    async def read(self) -> str | None:
        """See LinksFileSource.read."""
        try:
            return self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except UnicodeDecodeError as exc:
            raise LinksFileUnreadableError("it is not UTF-8 text") from exc
        except OSError as exc:
            raise LinksFileUnreadableError(exc.strerror or type(exc).__name__) from exc
