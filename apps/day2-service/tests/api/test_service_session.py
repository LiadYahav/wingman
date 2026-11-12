"""Day1's flavor rollout asks day2 for install MRs as an admin service session (ADR-0044).

Day1 issues the session itself, with the secret both services share and its
own short TTL (``wingman_day1.main``), for ``system:wingman-rollout`` with
the admin role; day2 trusts the role in the token, so the bulk install
needs no change. These tests pin that, and the title day1 reads back.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
from fastapi import FastAPI

from wingman_core.domain.mr_conventions import parse_mr_description
from wingman_core.domain.users import Role, User
from wingman_core.infrastructure.session_tokens import SessionTokens
from wingman_day2.settings import Config

ROLLOUT = User(username="system:wingman-rollout", role=Role.ADMIN)
DAY1_SERVICE_TOKEN_TTL = timedelta(minutes=5)
"""Day1's ``SERVICE_TOKEN_TTL``."""
CLUSTER = "ocp4-prod-herzi-site1"
MCE = "ocp4-prod-mce-site1-a"
BULK = f"/api/day2/clusters/{CLUSTER}/addons/bulk"


def day1_session(app: FastAPI, config: Config, clock: Any, user: User) -> httpx.AsyncClient:
    """A client holding a token issued as day1 issues its service sessions, not by day2."""
    tokens = SessionTokens(
        config.auth.jwt_secret_key.get_secret_value(), ttl=DAY1_SERVICE_TOKEN_TTL, clock=clock
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://day2",
        headers={"authorization": f"Bearer {tokens.issue(user)}"},
    )


def rollout_body() -> dict[str, Any]:
    """The bulk body day1's ``HttpDay2Installs`` sends: no version (ADR-0025)."""
    return {
        "addons": [
            {"team": "redbull", "addon": "bmhgen", "override_values": {"a": 1}},
            {"team": "falcon", "addon": "log-forwarder", "override_values": {}},
        ],
        "custom_message": "Flavor agent-baseline v1.1.0 needs these add-ons.",
    }


async def test_the_rollout_session_opens_install_mrs_in_its_own_name(
    app: FastAPI, config: Config, clock: Any, jane: httpx.AsyncClient
) -> None:
    async with day1_session(app, config, clock, ROLLOUT) as rollout:
        response = await rollout.post(BULK, params={"mce": MCE}, json=rollout_body())
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["failed"] == []
        opened = {mr["team"]: mr for mr in body["merge_requests"]}
        assert {team: mr["title"] for team, mr in opened.items()} == {
            "redbull": f"[Wingman/Day2] Install addon redbull/bmhgen on {CLUSTER}",
            "falcon": f"[Wingman/Day2] Install addon falcon/log-forwarder on {CLUSTER}",
        }
        for mr in opened.values():
            footer = parse_mr_description(mr["description"])
            assert footer is not None
            assert footer.author == ROLLOUT.username
            assert mr["author"]["username"] == ROLLOUT.username
            assert mr["source_branch"].startswith("platform/system-wingman-rollout/install-")
            assert "Flavor agent-baseline v1.1.0" in mr["description"]

        listed = await rollout.get("/api/day2/approvals")
        assert listed.status_code == 200, listed.text
        assert {(mr["team"], mr["iid"], mr["author"]["username"]) for mr in listed.json()} == {
            (team, mr["iid"], ROLLOUT.username) for team, mr in opened.items()
        }

    # A person approves the rollout's MR: it is not their own change.
    redbull = opened["redbull"]
    approved = await jane.post(
        f"/api/day2/approvals/redbull/{redbull['iid']}/approve", json={"sha": redbull["sha"]}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "merged"


async def test_a_viewer_service_session_cannot_install(
    app: FastAPI, config: Config, clock: Any
) -> None:
    # Day1's everyday service user reads as a viewer; the rollout needs its own admin session.
    viewer = User(username="system:wingman-day1", role=Role.VIEWER)
    async with day1_session(app, config, clock, viewer) as client:
        response = await client.post(BULK, params={"mce": MCE}, json=rollout_body())
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "FORBIDDEN"
        listed = await client.get("/api/day2/approvals")
        assert listed.json() == []


async def test_a_team_that_gave_wingman_no_write_access_refuses_the_rollout_with_its_code(
    app: FastAPI, config: Config, clock: Any
) -> None:
    # Day1 asks once per team and reads TEAM_READ_ONLY as that team's refusal (ADR-0043).
    body = {
        "addons": [{"team": "orca", "addon": "metrics", "override_values": {}}],
        "custom_message": "Flavor agent-baseline v1.1.0 needs these add-ons.",
    }
    async with day1_session(app, config, clock, ROLLOUT) as rollout:
        response = await rollout.post(BULK, params={"mce": MCE}, json=body)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "TEAM_READ_ONLY"
