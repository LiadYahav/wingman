"""OpenShiftOAuth against recorded-shape OAuth server and user API responses (MockTransport)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from prometheus_client import CollectorRegistry
from pydantic import SecretStr

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.auth import Identity
from wingman_day1.domain.errors import IdentityError, IdentityUnavailableError
from wingman_day1.infrastructure.fake_identity import FakeIdentityProvider
from wingman_day1.infrastructure.openshift_oauth import OpenShiftOAuth

SECRET = "client-secret-never-shown-0001"
CODE = "auth-code-never-shown-0001"
OPAQUE = "sha256~opaque-token-never-shown-0001"
API = "api.mgmt.example.invalid:6443"
OAUTH = "oauth-openshift.apps.mgmt.example.invalid"
REDIRECT = "https://wingman.example.invalid/login?from=oauth"

DISCOVERY = {
    "authorization_endpoint": f"https://{OAUTH}/oauth/authorize",
    "token_endpoint": f"https://{OAUTH}/oauth/token",
}
USER = {
    "metadata": {"name": "jane.doe", "uid": "u-1"},
    "fullName": "Jane Doe",
    "groups": ["wingman-admins", "devs"],
}

Route = Callable[[httpx.Request], httpx.Response]


class Server:
    """Routes by path; records every request."""

    def __init__(self, **routes: Route) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = {
            "/.well-known/oauth-authorization-server": "discovery",
            "/oauth/token": "token",
            "/apis/user.openshift.io/v1/users/~": "user",
            "/oauth2/token": "token",
        }.get(request.url.path, "other")
        return self.routes.get(key, lambda _r: httpx.Response(404))(request)


def json(status: int, body: object) -> Route:
    return lambda _request: httpx.Response(status, json=body)


def ok_server(**overrides: Route) -> Server:
    routes: dict[str, Route] = {
        "discovery": json(200, DISCOVERY),
        "token": json(200, {"access_token": OPAQUE, "token_type": "Bearer"}),
        "user": json(200, USER),
    }
    routes.update(overrides)
    return Server(**routes)


def make(
    server: Server,
    *,
    oauth_host: str = OAUTH,
    api_host: str = API,
    metrics: WingmanMetrics | None = None,
) -> OpenShiftOAuth:
    return OpenShiftOAuth(
        oauth_host=oauth_host,
        api_host=api_host,
        client_id="wingman",
        client_secret=SecretStr(SECRET),
        redirect_uri=REDIRECT,
        verify=False,
        timeout_seconds=2.0,
        metrics=metrics,
        transport=httpx.MockTransport(server),
        timer=iter(range(1000)).__next__,
    )


def assert_no_secrets(error: BaseException) -> None:
    text = str(error)
    for secret in (SECRET, CODE, OPAQUE):
        assert secret not in text


async def test_authorize_url_is_discovered_and_url_encoded() -> None:
    server = ok_server()
    oauth = make(server)
    url = await oauth.authorize_url()
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == DISCOVERY["authorization_endpoint"]
    assert parse_qs(parts.query) == {
        "client_id": ["wingman"],
        "redirect_uri": [REDIRECT],
        "response_type": ["code"],
        "scope": ["user:info"],
    }
    assert "redirect_uri=https%3A%2F%2Fwingman.example.invalid%2Flogin%3Ffrom%3Doauth" in url
    assert str(server.requests[0].url) == f"https://{API}/.well-known/oauth-authorization-server"
    await oauth.authorize_url()
    assert len(server.requests) == 1, "discovery is cached after it succeeds"
    await oauth.aclose()


async def test_an_endpoint_with_a_query_gets_its_parameters_appended() -> None:
    discovery = {**DISCOVERY, "authorization_endpoint": f"https://{OAUTH}/oauth/authorize?x=1"}
    oauth = make(ok_server(discovery=json(200, discovery)))
    assert (await oauth.authorize_url()).startswith(f"https://{OAUTH}/oauth/authorize?x=1&")


async def test_identify_exchanges_the_code_then_reads_the_user() -> None:
    server = ok_server()
    identity = await make(server).identify(CODE)
    assert identity == Identity(
        username="jane.doe", groups=("wingman-admins", "devs"), uid="u-1", full_name="Jane Doe"
    )
    _, token, user = server.requests
    assert (token.method, str(token.url)) == ("POST", DISCOVERY["token_endpoint"])
    assert parse_qs(token.content.decode()) == {
        "grant_type": ["authorization_code"],
        "code": [CODE],
        "redirect_uri": [REDIRECT],
        "client_id": ["wingman"],
        "client_secret": [SECRET],
    }
    assert token.headers["accept"] == "application/json"
    assert str(user.url) == f"https://{API}/apis/user.openshift.io/v1/users/~"
    assert user.headers["authorization"] == f"Bearer {OPAQUE}"


async def test_a_user_with_no_groups_or_name_fields_still_logs_in() -> None:
    identity = await make(ok_server(user=json(200, {"metadata": {"name": "bob"}}))).identify(CODE)
    assert identity == Identity(username="bob")


async def test_discovery_failure_falls_back_to_the_oauth_host_and_retries_later() -> None:
    server = ok_server(discovery=json(503, {}))
    oauth = make(server)
    assert (await oauth.authorize_url()).startswith(f"https://{OAUTH}/oauth/authorize?")
    assert (await oauth.identify(CODE)).username == "jane.doe"
    token = server.requests[2]
    assert str(token.url) == f"https://{OAUTH}/oauth/token"
    paths = [r.url.path for r in server.requests]
    assert paths.count("/.well-known/oauth-authorization-server") == 2


@pytest.mark.parametrize(
    "discovery",
    [
        json(200, {"authorization_endpoint": "https://x.example.invalid/a"}),
        json(200, ["not", "a", "mapping"]),
        lambda _r: httpx.Response(200, content=b"not json"),
    ],
)
async def test_without_an_oauth_host_a_bad_discovery_is_an_identity_error(
    discovery: Route,
) -> None:
    oauth = make(ok_server(discovery=discovery), oauth_host="")
    with pytest.raises(IdentityError, match="discovery"):
        await oauth.authorize_url()


async def test_hosts_may_carry_a_scheme_or_a_trailing_slash() -> None:
    server = ok_server()
    oauth = make(server, api_host=f"https://{API}/", oauth_host=f"https://{OAUTH}/")
    await oauth.authorize_url()
    assert str(server.requests[0].url) == f"https://{API}/.well-known/oauth-authorization-server"


async def test_without_an_api_host_nothing_can_be_discovered_or_read() -> None:
    server = ok_server()
    oauth = make(server, api_host="")
    assert (await oauth.authorize_url()).startswith(f"https://{OAUTH}/oauth/authorize?")
    with pytest.raises(IdentityError, match="OPENSHIFT_API_HOST"):
        await oauth.identify(CODE)
    no_hosts = make(server, api_host="", oauth_host="")
    with pytest.raises(IdentityError, match="OPENSHIFT_API_HOST"):
        await no_hosts.authorize_url()


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        (
            {"token": json(401, {"error": f"invalid_grant {CODE}"})},
            r"refused the credentials \(401\)",
        ),
        ({"token": json(400, {"error": f"bad {SECRET}"})}, "answered 400"),
        ({"token": json(200, {"token_type": "Bearer"})}, "no access_token"),
        ({"token": json(200, ["x"])}, "no access_token"),
        ({"user": json(401, {"message": f"token {OPAQUE} expired"})}, r"user lookup.*401"),
        ({"user": json(500, {})}, "answered 500"),
        ({"user": json(200, {"metadata": {"name": "  "}})}, "no username"),
        ({"user": json(200, {"metadata": "x"})}, "no username"),
        ({"user": json(200, ["x"])}, "no username"),
        ({"user": json(200, {**USER, "groups": "admins"})}, "groups"),
        ({"user": json(200, {**USER, "groups": [1]})}, "groups"),
        ({"user": lambda _r: httpx.Response(200, content=b"<html>")}, "not JSON"),
    ],
)
async def test_every_failure_is_an_identity_error_without_secrets(
    overrides: dict[str, Route], match: str
) -> None:
    with pytest.raises(IdentityError, match=match) as caught:
        await make(ok_server(**overrides)).identify(CODE)
    assert_no_secrets(caught.value)


@pytest.mark.parametrize("exc", [httpx.ConnectError, httpx.ReadTimeout])
async def test_transport_failures_are_identity_errors_without_secrets(
    exc: type[httpx.TransportError],
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exc(f"boom {SECRET} {CODE} {OPAQUE}", request=request)

    with pytest.raises(IdentityUnavailableError, match="unreachable") as caught:
        await make(ok_server(token=fail)).identify(CODE)
    assert_no_secrets(caught.value)
    assert exc.__name__ in str(caught.value)


async def test_an_openshift_server_error_is_unavailable_not_a_refusal() -> None:
    # 5xx means OpenShift is down (counted as `unavailable`, answered 502), not "wrong code".
    with pytest.raises(IdentityUnavailableError, match="answered 503"):
        await make(ok_server(user=json(503, {}))).identify(CODE)
    with pytest.raises(IdentityError) as refused:
        await make(ok_server(token=json(400, {}))).identify(CODE)
    assert not isinstance(refused.value, IdentityUnavailableError)


async def test_an_empty_code_is_refused_before_any_request() -> None:
    server = ok_server()
    with pytest.raises(IdentityError, match="no authorization code"):
        await make(server).identify("  ")
    assert server.requests == []


async def test_logins_are_counted_by_step_and_outcome() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), service="day1", version="t", commit="t")
    await make(ok_server(), metrics=metrics).identify(CODE)
    with pytest.raises(IdentityError):
        await make(ok_server(token=json(401, {})), metrics=metrics).identify(CODE)
    total = "wingman_dependency_requests_total"
    labels = {"dependency": "openshift_oauth"}

    def count(operation: str, outcome: str) -> float | None:
        return metrics.registry.get_sample_value(
            total, {**labels, "operation": operation, "outcome": outcome}
        )

    assert count("discover", "ok") == 2
    assert count("exchange_code", "ok") == 1
    assert count("exchange_code", "denied") == 1
    assert count("get_user", "ok") == 1


def test_a_ca_bundle_path_is_loaded_at_construction(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        OpenShiftOAuth(
            oauth_host=OAUTH,
            api_host=API,
            client_id="wingman",
            client_secret=SecretStr(SECRET),
            redirect_uri=REDIRECT,
            verify=str(tmp_path / "missing.pem"),
        )


async def test_fake_identity_provider_maps_codes_to_identities() -> None:
    jane = Identity(username="jane.doe", groups=("wingman-admins",))
    fake = FakeIdentityProvider({"good-code": jane})
    assert await fake.identify("good-code") == jane
    assert (await fake.authorize_url()).startswith("https://oauth.example.invalid/")
    with pytest.raises(IdentityError):
        await fake.identify("bad-code")
    custom = FakeIdentityProvider({}, authorize_url="https://elsewhere.example.invalid/a")
    assert await custom.authorize_url() == "https://elsewhere.example.invalid/a"
