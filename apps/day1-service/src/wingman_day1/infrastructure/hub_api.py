"""HttpHubApi: the MCE hub Kubernetes APIs over httpx, read only.

HostedClusters, NodePools and InfraEnvs (live status), and each cluster's
Machines, MachineSets, AgentMachines and Agents (its nodes by NodePool,
ADR-0038). CAPI is always asked for ``cluster.x-k8s.io/v1beta1``: every MCE
from 4.16 serves it, and 4.16 to 4.18 serve nothing newer.

Each MCE hub has its own API server and its own service-account token,
mounted as a YAML file (``MCE_TOKENS_FILE``): the legacy ``{<mce>: <token>}``,
or ``{<mce>: {token: <token>, url: https://<host>[:<port>]}}`` for a hub whose
address is not the convention's ``https://api.<mce>.<domain>:6443``
(ADR-0045). The legacy service used the synchronous kubernetes client in a
thread; these are plain GETs, so this is async httpx with explicit timeouts,
like the GitLab adapter (ADR-0002).

Errors are day1 domain errors. A token never appears in an error or a log
line: messages name the MCE and the resource path only.
"""

from __future__ import annotations

import ssl
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol
from urllib.parse import urlsplit

import httpx
import yaml

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.errors import (
    HubDeniedError,
    HubNotConfiguredError,
    HubObjectNotFoundError,
    HubUnavailableError,
)
from wingman_day1.domain.machines import (
    DEPLOYMENT_NAME_LABEL,
    NODE_POOL_ANNOTATION,
    REVISION_ANNOTATION,
    SET_NAME_LABEL,
    UPGRADE_DEGRADED_ANNOTATION,
    UPGRADE_IN_PROGRESS_ANNOTATION,
    AgentMachineObservation,
    AgentObservation,
    MachineObservation,
    MachineSetObservation,
)
from wingman_day1.domain.names import dns_label_problems
from wingman_day1.domain.selectors import LabelRequirement, LabelSelector, Operator
from wingman_day1.domain.status import (
    Autoscaling,
    Condition,
    HostedClusterObservation,
    NodePoolObservation,
)
from wingman_day1.infrastructure.observed import HubOperation, Observer, Timer

_HYPERSHIFT: Final = "/apis/hypershift.openshift.io/v1beta1"
_AGENT_INSTALL: Final = "/apis/agent-install.openshift.io/v1beta1"
_CAPI: Final = "/apis/cluster.x-k8s.io/v1beta1"
_CAPI_AGENT: Final = "/apis/capi-provider.agent-install.openshift.io/v1beta1"
_API_PORT: Final = 6443

JSON = Any
"""A decoded Kubernetes JSON value; narrowed by the parsers below."""


class Named(Protocol):
    """An object a list is sorted by: it has a name."""

    @property
    def name(self) -> str:
        """Its ``metadata.name``."""
        ...


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
        urls: Mapping[str, str] | None = None,
        verify: bool | str = True,
        timeout_seconds: float = 10.0,
        metrics: WingmanMetrics | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Reach each MCE at its ``urls`` entry, else ``https://api.<mce>.<domain>:6443``.

        No ``.<domain>`` when it is empty. ``transport`` replaces the network in tests.
        """
        self._tokens = dict(tokens)
        self._urls = dict(urls or {})
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

    async def machines(self, mce: str, *, namespace: str) -> list[MachineObservation]:
        """See HubApi.machines."""
        return await self._observer.call(
            HubOperation.LIST_MACHINES,
            self._list(mce, namespace, f"{_CAPI}/namespaces/{namespace}/machines", machine_from),
        )

    async def machine_sets(self, mce: str, *, namespace: str) -> list[MachineSetObservation]:
        """See HubApi.machine_sets."""
        path = f"{_CAPI}/namespaces/{namespace}/machinesets"
        return await self._observer.call(
            HubOperation.LIST_MACHINE_SETS, self._list(mce, namespace, path, machine_set_from)
        )

    async def agent_machines(self, mce: str, *, namespace: str) -> list[AgentMachineObservation]:
        """See HubApi.agent_machines."""
        path = f"{_CAPI_AGENT}/namespaces/{namespace}/agentmachines"
        return await self._observer.call(
            HubOperation.LIST_AGENT_MACHINES, self._list(mce, namespace, path, agent_machine_from)
        )

    async def agents(self, mce: str, *, namespace: str) -> list[AgentObservation]:
        """See HubApi.agents."""
        path = f"{_AGENT_INSTALL}/namespaces/{namespace}/agents"
        return await self._observer.call(
            HubOperation.LIST_AGENTS, self._list(mce, namespace, path, agent_from)
        )

    # ── Calls ───────────────────────────────────────────────────────────────

    async def _hosted_cluster(
        self, mce: str, namespace: str, name: str
    ) -> HostedClusterObservation:
        _object_name("namespace", namespace)
        _object_name("HostedCluster", name)
        raw = await self._get(mce, f"{_HYPERSHIFT}/namespaces/{namespace}/hostedclusters/{name}")
        try:
            return hosted_cluster_from(raw, namespace=namespace, name=name)
        except (KeyError, TypeError, ValueError) as exc:
            raise HubUnavailableError(
                f"MCE {mce!r} returned a malformed HostedCluster {namespace}/{name}"
            ) from exc

    async def _node_pools(self, mce: str, namespace: str) -> list[NodePoolObservation]:
        _object_name("namespace", namespace)
        raw = await self._get(mce, f"{_HYPERSHIFT}/namespaces/{namespace}/nodepools")
        try:
            pools = [node_pool_from(item) for item in _items(raw)]
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

    async def _list[T: Named](
        self, mce: str, namespace: str, path: str, parse: Callable[[JSON], T]
    ) -> list[T]:
        """A namespaced list, parsed and sorted by name.

        A namespace that does not exist lists as empty. A 404 means the hub
        does not serve the resource at all: the hub's fault, not a missing
        cluster's.
        """
        _object_name("namespace", namespace)
        try:
            raw = await self._get(mce, path)
        except HubObjectNotFoundError as exc:
            raise HubUnavailableError(f"MCE {mce!r} does not serve GET {path} (404)") from exc
        try:
            parsed = [parse(item) for item in _items(raw)]
        except (KeyError, TypeError, ValueError) as exc:
            raise HubUnavailableError(
                f"MCE {mce!r} returned a malformed list on GET {path}"
            ) from exc
        return sorted(parsed, key=lambda item: item.name)

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
        client = httpx.AsyncClient(
            base_url=self._base_url(mce),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=self._timeout,
            verify=self._verify,
            transport=self._transport,
        )
        self._clients[mce] = client
        return client

    def _base_url(self, mce: str) -> str:
        """The MCE's own address from the tokens file, else the convention's (ADR-0045)."""
        url = self._urls.get(mce)
        if url is not None:
            return url
        if dns_label_problems(mce, what="MCE"):
            raise HubNotConfiguredError(f"MCE {mce!r} is not a DNS label; no hub address for it")
        host = f"api.{mce}.{self._domain}" if self._domain else f"api.{mce}"
        return f"https://{host}:{_API_PORT}"

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


def _strings(value: JSON, what: str) -> dict[str, str]:
    mapping = _mapping(value)
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()):
        raise TypeError(f"{what} is not a map of strings")
    return mapping


def _metadata(raw: JSON) -> tuple[dict[str, JSON], dict[str, str], dict[str, str]]:
    """``metadata``, its labels and its annotations."""
    metadata = _mapping(_mapping(raw).get("metadata"))
    return (
        metadata,
        _strings(metadata.get("labels"), "metadata.labels"),
        _strings(metadata.get("annotations"), "metadata.annotations"),
    )


def hosted_cluster_from(raw: JSON, *, namespace: str, name: str) -> HostedClusterObservation:
    """A HostedCluster (``hypershift.openshift.io/v1beta1``)."""
    spec = _mapping(_mapping(raw).get("spec"))
    agent = _mapping(_mapping(spec.get("platform")).get("agent"))
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
        agent_namespace=_text(agent.get("agentNamespace")),
    )


def node_pool_from(raw: JSON) -> NodePoolObservation:
    """A NodePool (``hypershift.openshift.io/v1beta1``)."""
    pool = _mapping(raw)
    spec = _mapping(pool.get("spec"))
    status = _mapping(pool.get("status"))
    current = _replicas(status.get("replicas"))
    desired = _replicas(spec.get("replicas"))
    scaling = spec.get("autoScaling")
    autoscaling = None
    if scaling is not None:
        bounds = _mapping(scaling)
        autoscaling = Autoscaling(
            min=_replicas(bounds.get("min")) or 0, max=_replicas(bounds["max"]) or 0
        )
    platform = _mapping(_mapping(spec.get("platform")).get("agent"))
    return NodePoolObservation(
        name=_metadata_name(pool),
        desired_replicas=desired if desired is not None else (current or 0),
        current_replicas=current or 0,
        conditions=_conditions(status),
        replicas=desired,
        autoscaling=autoscaling,
        upgrade_type=_text(_mapping(spec.get("management")).get("upgradeType")),
        version=_text(status.get("version")),
        agent_selector=label_selector_from(platform.get("agentLabelSelector")),
    )


def label_selector_from(raw: JSON) -> LabelSelector | None:
    """A ``metav1.LabelSelector``; ``None`` when absent. An unknown operator is malformed."""
    if raw is None:
        return None
    selector = _mapping(raw)
    expressions = selector.get("matchExpressions") or []
    if not isinstance(expressions, list):
        raise TypeError("matchExpressions is not a list")
    requirements = []
    for item in expressions:
        expression = _mapping(item)
        values = expression.get("values") or []
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise TypeError("matchExpressions values is not a list of strings")
        requirements.append(
            LabelRequirement(
                key=str(expression["key"]),
                operator=Operator(expression["operator"]),
                values=tuple(values),
            )
        )
    labels = _strings(selector.get("matchLabels"), "matchLabels")
    return LabelSelector(
        match_labels=tuple(sorted(labels.items())), match_expressions=tuple(requirements)
    )


def machine_from(raw: JSON) -> MachineObservation:
    """A CAPI Machine (``cluster.x-k8s.io/v1beta1``)."""
    metadata, labels, annotations = _metadata(raw)
    spec = _mapping(_mapping(raw).get("spec"))
    status = _mapping(_mapping(raw).get("status"))
    return MachineObservation(
        name=_metadata_name(raw),
        node_pool=_text(annotations.get(NODE_POOL_ANNOTATION)),
        machine_set=_text(labels.get(SET_NAME_LABEL)),
        infrastructure_ref=_text(_mapping(spec.get("infrastructureRef")).get("name")),
        provider_id=_text(spec.get("providerID")),
        phase=_text(status.get("phase")),
        node_name=_text(_mapping(status.get("nodeRef")).get("name")),
        deleting=bool(metadata.get("deletionTimestamp")),
        failure_reason=_text(status.get("failureReason")),
        failure_message=_text(status.get("failureMessage")),
        conditions=_conditions(status),
        v1beta2_conditions=_conditions(_mapping(status.get("v1beta2"))),
    )


def machine_set_from(raw: JSON) -> MachineSetObservation:
    """A CAPI MachineSet (``cluster.x-k8s.io/v1beta1``)."""
    _, labels, annotations = _metadata(raw)
    revision = annotations.get(REVISION_ANNOTATION)
    return MachineSetObservation(
        name=_metadata_name(raw),
        node_pool=_text(annotations.get(NODE_POOL_ANNOTATION)),
        deployment=_text(labels.get(DEPLOYMENT_NAME_LABEL)),
        revision=int(revision) if revision else None,
        upgrade_in_progress=_text(annotations.get(UPGRADE_IN_PROGRESS_ANNOTATION)),
        upgrade_degraded=_text(annotations.get(UPGRADE_DEGRADED_ANNOTATION)),
    )


def agent_machine_from(raw: JSON) -> AgentMachineObservation:
    """An AgentMachine (``capi-provider.agent-install.openshift.io/v1beta1``)."""
    status = _mapping(_mapping(raw).get("status"))
    return AgentMachineObservation(
        name=_metadata_name(raw),
        agent_name=_text(_mapping(status.get("agentRef")).get("name")),
        conditions=_conditions(status),
    )


def agent_from(raw: JSON) -> AgentObservation:
    """An Agent (``agent-install.openshift.io/v1beta1``)."""
    _, labels, _ = _metadata(raw)
    spec = _mapping(_mapping(raw).get("spec"))
    status = _mapping(_mapping(raw).get("status"))
    inventory = _mapping(status.get("inventory"))
    interfaces = inventory.get("interfaces") or []
    if not isinstance(interfaces, list):
        raise TypeError("status.inventory.interfaces is not a list")
    macs = [_text(_mapping(item).get("macAddress")) for item in interfaces]
    return AgentObservation(
        name=_metadata_name(raw),
        labels=labels,
        approved=spec.get("approved") is True,
        hostname=_text(spec.get("hostname")) or _text(inventory.get("hostname")),
        state=_text(_mapping(status.get("debugInfo")).get("state")),
        stage=_text(_mapping(status.get("progress")).get("currentStage")),
        serial=_text(_mapping(inventory.get("systemVendor")).get("serialNumber")),
        macs=tuple(mac.lower() for mac in macs if mac),
        conditions=_conditions(status),
    )
