"""Route dependencies: the use cases the composition root put on ``app.state``."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from wingman_day2.application.services import Day2Services


def services(request: Request) -> Day2Services:
    """The day2 use cases."""
    return request.app.state.day2


Services = Annotated[Day2Services, Depends(services)]
