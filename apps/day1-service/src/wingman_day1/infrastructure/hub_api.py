"""HttpHubApi: the MCE hub Kubernetes APIs (HostedClusters, NodePools, InfraEnvs) over httpx.

Each MCE hub has its own API server, ``https://api.<mce>.<domain>:6443``,
and its own service-account token, mounted as the legacy YAML file
``{<mce-name>: <token>}`` (``MCE_TOKENS_FILE``). The legacy service used the
synchronous kubernetes client in a thread; these are three GETs, so this is
plain async httpx with explicit timeouts, like the GitLab adapter (ADR-0002).

Errors are day1 domain errors. A token never appears in an error or a log
line: messages name the MCE and the resource path only.
"""

from __future__ import annotations

import ssl
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import httpx
import yaml

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.errors import (
    HubDeniedError,
    HubNotConfiguredError,
    HubObjectNotFoundError,
    HubUnavailableError,
)
from wingman_day1.domain.names import dns_label_problems
from wingman_day1.domain.status import Condition, HostedClusterObservation, NodePoolObservation
from wingman_day1.infrastructure.observed import HubOperation, Observer, Timer

_HYPERSHIFT: Final = "/apis/hypershift.openshift.io/v1beta1"
_AGENT_INSTALL: Final = "/apis/agent-install.openshift.io/v1beta1"
_API_PORT: Final = 6443

JSON = Any
"""A decoded Kubernetes JSON value; narrowed by the parsers below."""


def load_mce_tokens(path: Path) -> dict[str, str]:
    """Read the legacy token file: a YAML mapping of MCE name to service-account token.

    Raises ``ValueError`` (naming the MCE key, never the token) for anything
    that is not a mapping of non-empty, single-line strings; an empty file
    means no MCE is configured.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(  # noqa: TRY004 - a bad settings file is one ValueError to start-up
            f"{path} must be a YAML mapping of MCE name to token"
        )
    tokens: dict[str, str] = {}
    for mce, token in raw.items():
        if not isinstance(mce, str) or not mce.strip():
            raise ValueError(f"{path}: every key must be an MCE name")
        if not isinstance(token, str) or not token.strip():
            raise ValueError(f"{path}: the token for MCE {mce!r} is empty or not a string")
        if "\r" in token or "\n" in token.strip():
            raise ValueError(f"{path}: the token for MCE {mce!r} spans more than one line")
        tokens[mce] = token.strip()
    return tokens


def _ssl_context(verify: bool | str) -> ssl.SSLContext | bool:
    """``True``/``False``, or a context trusting the CA bundle at ``verify``.

    Built eagerly so a CA bundle path that does not exist stops start-up.
    """
    if isinstance(verify, bool):
        return verify
    return ssl.create_default_context(cafile=verify)


class HttpHubApi:
    """A ``HubApi`` for every MCE that has a token, one lazily built client per MCE."""

    def __init__(
        self,
        *,
        tokens: Mapping[str, str],
        domain: str,
        verify: bool | str = True,
        timeout_seconds: float = 10.0,
        metrics: WingmanMetrics | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Reach ``https://api.<mce>.<domain>:6443`` (no ``.<domain>`` when it is empty).

        ``transport`` replaces the network in tests.
        """
        self._tokens = dict(tokens)
        self._domain = domain.strip().strip(".")
        self._verify = _ssl_context(verify)
        self._timeout = httpx.Timeout(timeout_seconds)
        self._transport = transport
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._observer = Observer(Dependency.KUBERNETES, metrics, timer=timer)

    async def aclose(self) -> None:
        """Close every client built so far."""
        clients, self._clients = list(self._clients.values()), {}
        for client in clients:
            await client.aclose()

    async def hosted_cluster(
        self, mce: str, *, namespace: str, name: str
    ) -> HostedClusterObservation:
        """See HubApi.hosted_cluster."""
        return await self._observer.call(
            HubOperation.GET_HOSTED_CLUSTER, self._hosted_cluster(mce, namespace, name)
        )

    async def node_pools(self, mce: str, *, namespace: str) -> list[NodePoolObservation]:
        """See HubApi.node_pools."""
        return await self._observer.call(
            HubOperation.LIST_NODE_POOLS, self._node_pools(mce, namespace)
        )

    async def infra_envs(self, mce: str, *, namespace: str | None) -> list[str]:
        """See HubApi.infra_envs."""
        return await self._observer.call(
            HubOperation.LIST_INFRA_ENVS, self._infra_envs(mce, namespace or None)
        )

    # ── Calls ───────────────────────────────────────────────────────────────

    async def _hosted_cluster(
        self, mce: str, namespace: str, name: str
    ) -> HostedClusterObservation:
        _object_name("namespace", namespace)
        _object_name("HostedCluster", name)
        raw = await self._get(mce, f"{_HYPERSHIFT}/namespaces/{namespace}/hostedclusters/{name}")
        try:
            return _hosted_cluster(raw, namespace=namespace, name=name)
        except (KeyError, TypeError, ValueError) as exc:
            raise HubUnavailableError(
                f"MCE {mce!r} returned a malformed HostedCluster {namespace}/{name}"
            ) from exc

    async def _node_pools(self, mce: str, namespace: str) -> list[NodePoolObservation]:
        _object_name("namespace", namespace)
        raw = await self._get(mce, f"{_HYPERSHIFT}/namespaces/{namespace}/nodepools")
        try:
            pools = [_node_pool(item) for item in _items(raw)]
        except (KeyError, TypeError, ValueError) as exc:
            raise HubUnavailableError(
                f"MCE {mce!r} returned a malformed NodePool list in {namespace}"
            ) from exc
        return sorted(pools, key=lambda pool: pool.name)

    async def _infra_envs(self, mce: str, namespace: str | None) -> list[str]:
        if namespace is None:
            path = f"{_AGENT_INSTALL}/infraenvs"
        else:
            _object_name("namespace", namespace)
            path = f"{_AGENT_INSTALL}/namespaces/{namespace}/infraenvs"
        raw = await self._get(mce, path)
        try:
            names = [_metadata_name(item) for item in _items(raw)]
        except (KeyError, TypeError, ValueError) as exc:
            raise HubUnavailableError(f"MCE {mce!r} returned a malformed InfraEnv list") from exc
        return sorted(names)

    # ── HTTP ────────────────────────────────────────────────────────────────

    def _client(self, mce: str) -> httpx.AsyncClient:
        client = self._clients.get(mce)
        if client is not None:
            return client
        token = self._tokens.get(mce)
        if token is None:
            configured = ", ".join(sorted(self._tokens)) or "(none)"
            raise HubNotConfiguredError(
                f"no service-account token is configured for MCE {mce!r}; "
                f"configured MCEs: {configured}"
            )
        if dns_label_problems(mce, what="MCE"):
            raise HubNotConfiguredError(f"MCE {mce!r} is not a DNS label; no hub address for it")
        host = f"api.{mce}.{self._domain}" if self._domain else f"api.{mce}"
        client = httpx.AsyncClient(
            base_url=f"https://{host}:{_API_PORT}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=self._timeout,
            verify=self._verify,
            transport=self._transport,
        )
        self._clients[mce] = client
        return client

    async def _get(self, mce: str, path: str) -> JSON:
        client = self._client(mce)
        try:
            response = await client.get(path)
        except httpx.TransportError as exc:
            raise HubUnavailableError(
                f"MCE {mce!r} hub API unreachable on GET {path}: {type(exc).__name__}"
            ) from exc
        status = response.status_code
        if status in (401, 403):
            reason = "rejected Wingman's token" if status == 401 else "denied Wingman's token"
            raise HubDeniedError(f"MCE {mce!r} hub API {reason} ({status}) on GET {path}")
        if status == 404:
            raise HubObjectNotFoundError(f"MCE {mce!r} has no {path} (404)")
        if not response.is_success:
            raise HubUnavailableError(f"MCE {mce!r} hub API answered {status} on GET {path}")
        try:
            return response.json()
        except ValueError as exc:
            raise HubUnavailableError(
                f"MCE {mce!r} hub API answered GET {path} with a body that is not JSON"
            ) from exc


def _object_name(what: str, value: str) -> None:
    """Names go into URL paths; a name that is not a DNS label cannot exist on the hub."""
    if dns_label_problems(value, what=what):
        raise HubObjectNotFoundError(f"{what} {value!r} is not a DNS label, so it cannot exist")


# ── Parsing Kubernetes objects into domain types ─────────────────────────────


def _mapping(value: JSON) -> dict[str, JSON]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"expected an object, got {type(value).__name__}")
    return value


def _items(raw: JSON) -> list[JSON]:
    items = _mapping(raw).get("items") or []
    if not isinstance(items, list):
        raise TypeError("items is not a list")
    return items


def _metadata_name(raw: JSON) -> str:
    name = _mapping(_mapping(raw)["metadata"])["name"]
    if not isinstance(name, str) or not name:
        raise ValueError("metadata.name is missing")
    return name


def _text(value: JSON) -> str | None:
    return value if isinstance(value, str) and value else None


def _replicas(value: JSON) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"replicas {value!r} is not a non-negative integer")
    return value


def _conditions(status: dict[str, JSON]) -> tuple[Condition, ...]:
    raw = status.get("conditions") or []
    if not isinstance(raw, list):
        raise TypeError("status.conditions is not a list")
    conditions: list[Condition] = []
    for item in raw:
        condition = _mapping(item)
        conditions.append(
            Condition(
                type=str(condition["type"]),
                status=str(condition.get("status", "")),
                reason=str(condition.get("reason") or ""),
                message=str(condition.get("message") or ""),
            )
        )
    return tuple(conditions)


def _hosted_cluster(raw: JSON, *, namespace: str, name: str) -> HostedClusterObservation:
    status = _mapping(_mapping(raw).get("status"))
    history = _mapping(status.get("version")).get("history") or []
    if not isinstance(history, list):
        raise TypeError("status.version.history is not a list")
    version = _text(_mapping(history[0]).get("version")) if history else None
    return HostedClusterObservation(
        name=name,
        namespace=namespace,
        phase=_text(status.get("phase")),
        version=version,
        conditions=_conditions(status),
    )


def _node_pool(raw: JSON) -> NodePoolObservation:
    pool = _mapping(raw)
    spec = _mapping(pool.get("spec"))
    status = _mapping(pool.get("status"))
    current = _replicas(status.get("replicas"))
    desired = _replicas(spec.get("replicas"))
    return NodePoolObservation(
        name=_metadata_name(pool),
        desired_replicas=desired if desired is not None else (current or 0),
        current_replicas=current or 0,
        conditions=_conditions(status),
    )
