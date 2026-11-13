"""Wingman's own INFO records reach stderr; other libraries' only from WARNING up."""

from __future__ import annotations

import logging

import pytest

from wingman_core.observability.logs import WingmanOrWarning, emit_wingman_logs


def record(name: str, level: int) -> logging.LogRecord:
    return logging.LogRecord(name, level, __file__, 1, "message", None, None)


@pytest.mark.parametrize(
    ("name", "level", "written"),
    [
        ("wingman_day1.application.nodes", logging.INFO, True),
        ("wingman_core.infrastructure.warm_up", logging.INFO, True),
        ("wingman_day1.application.server_scan", logging.DEBUG, False),
        ("httpx", logging.INFO, False),
        ("httpx", logging.WARNING, True),
        ("asyncio", logging.ERROR, True),
    ],
)
def test_wingman_from_info_and_everyone_from_warning(name: str, level: int, written: bool) -> None:
    assert WingmanOrWarning().filter(record(name, level)) is written


def test_a_person_record_reaches_stderr_once(capsys: pytest.CaptureFixture[str]) -> None:
    emit_wingman_logs()
    emit_wingman_logs()
    logging.getLogger("wingman_day1.application.server_scan").info(
        "server maintenance started: user=alice server_id=srv_1"
    )
    logging.getLogger("httpx").info("HTTP Request: GET http://server-scan.test")
    err = capsys.readouterr().err
    assert err.count("server maintenance started: user=alice server_id=srv_1") == 1
    assert "INFO wingman_day1.application.server_scan:" in err
    assert "HTTP Request" not in err
