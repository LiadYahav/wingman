"""Wingman's own log records reach the pod's log (stderr).

The services run under uvicorn, which configures only its own loggers, and
Python's root logger has no handler: a record below WARNING was dropped. The
INFO records are the ones that say what a person did (a node uninstall
started, a cluster's merge request opened, a server's maintenance changed,
with the person's name), so they never reached the log.

``emit_wingman_logs`` gives the root logger one stderr handler at INFO that
passes Wingman's own records (loggers named ``wingman_*``) from INFO up and
every other library's from WARNING up, as before: httpx's per-request INFO
lines stay out. Called by ``create_base_app``; a second call changes nothing.
"""

from __future__ import annotations

import logging
import sys
from typing import Final

WINGMAN_LOGGERS: Final = "wingman_"
"""The prefix of every Wingman package's logger name (``wingman_day1.application.nodes``)."""
FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class WingmanOrWarning(logging.Filter):
    """Wingman's records from INFO up; any other library's from WARNING up."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Whether ``record`` is written."""
        if record.levelno >= logging.WARNING:
            return True
        return record.levelno >= logging.INFO and record.name.startswith(WINGMAN_LOGGERS)


class _WingmanHandler(logging.StreamHandler):
    """The one handler ``emit_wingman_logs`` adds; its type marks it as added."""

    def emit(self, record: logging.LogRecord) -> None:
        """Write to ``sys.stderr`` as it is now (a test runner replaces it)."""
        self.stream = sys.stderr
        super().emit(record)


def emit_wingman_logs() -> None:
    """Write Wingman's INFO records and everyone's warnings to stderr, once per process."""
    root = logging.getLogger()
    if any(isinstance(handler, _WingmanHandler) for handler in root.handlers):
        return
    handler = _WingmanHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(FORMAT))
    handler.addFilter(WingmanOrWarning())
    root.addHandler(handler)
    if root.level > logging.INFO:
        root.setLevel(logging.INFO)
