"""HttpHubApi: the MCE hub Kubernetes APIs over httpx, read only.

HostedClusters, NodePools and InfraEnvs (live status), each cluster's
Machines, MachineSets, AgentMachines and Agents (its nodes by NodePool,
ADR-0038), and the hub's own nodes and pods (placement's free pods,
ADR-0050). CAPI is always asked for ``cluster.x-k8s.io/v1beta1``: every MCE
from 4.16 serves it, and 4.16 to 4.18 serve nothing newer.

An MCE runs thousands of pods, and a pod object is kilobytes. Placement
needs only each pod's node, so pods are listed in Kubernetes' Table form
(one short row per pod, no object), only those that are not ``Succeeded`` or
``Failed``, a page at a time (ADR-0050 has the sizes).

Each MCE hub has its own API server and its own service-account token, read
from the tokens file (``infrastructure/mce_access.py``, ADR-0045). The legacy
service used the synchronous kubernetes client in a thread; these are plain
GETs, so this is async httpx with explicit timeouts, like the GitLab adapter
(ADR-0002).

Errors are day1 domain errors. A token never appears in an error or a log
line: messages name the MCE and the resource path only. The objects are
parsed in ``infrastructure/hub_objects.py``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Final, Protocol

import httpx

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.errors import (
    HubDeniedError,
    HubNotConfiguredError,
    HubObjectNotFoundError,
    HubUnavailableError,
)
from wingman_day1.domain.infra_env_pools import InfraEnvObservation
from wingman_day1.domain.machines import (
    INFRA_ENV_LABEL,
    AgentMachineObservation,
    AgentObservation,
    MachineObservation,
    MachineSetObservation,
)
from wingman_day1.domain.mce_capacity import NodeObservation
from wingman_day1.domain.names import dns_label_problems
from wingman_day1.domain.status import HostedClusterObservation, NodePoolObservation
from wingman_day1.infrastructure.http import JSON, tls_verify
from wingman_day1.infrastructure.hub_objects import (
    agent_from,
    agent_machine_from,
    continue_token,
    hosted_cluster_from,
    infra_env_from,
    list_items,
    machine_from,
    machine_set_from,
    node_from,
    node_pool_from,
    pods_per_node_from,
)
from wingman_day1.infrastructure.observed import HubOperation, Observer, Timer

_HYPERSHIFT: Final = "/apis/hypershift.openshift.io/v1beta1"
_AGENT_INSTALL: Final = "/apis/agent-install.openshift.io/v1beta1"
_CAPI: Final = "/apis/cluster.x-k8s.io/v1beta1"
_CAPI_AGENT: Final = "/apis/capi-provider.agent-install.openshift.io/v1beta1"
_CORE: Final = "/api/v1"
_API_PORT: Final = 6443
PAGE_SIZE: Final = 500
"""Objects per list page (``limit``); the API server pages the rest with ``continue``."""
MAX_PAGES: Final = 400
"""A list that is still paging after this many pages is refused as unavailable."""
TABLE: Final = "application/json;as=Table;v=v1;g=meta.k8s.io"
"""The Accept header for a list as Table rows, without the objects (``includeObject=None``)."""
NON_TERMINAL_PODS: Final = "status.phase!=Succeeded,status.phase!=Failed"
"""The field selector for pods that still take a slot on their node."""


class Named(Protocol):
    """An object a list is sorted by: it has a name."""

    @property
    def name(self) -> str:
        """Its ``metadata.name``."""
        ...


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
        self._verify = tls_verify(verify)
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

    async def infra_envs(self, mce: str, *, namespace: str | None) -> list[InfraEnvObservation]:
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

    async def nodes(self, mce: str) -> list[NodeObservation]:
        """See HubApi.nodes: the full Node objects, a page at a time."""
        pages = await self._paged(
            mce, f"{_CORE}/nodes", HubOperation.LIST_NODES, params={}, accept=None, parse=_nodes
        )
        return sorted((node for page in pages for node in page), key=lambda node: node.name)

    async def infra_env_agents(
        self, mce: str, *, infra_envs: Sequence[str], namespace: str | None
    ) -> list[AgentObservation]:
        """See HubApi.infra_env_agents: the Agents whose InfraEnv label is one of these, paged."""
        for infra_env in infra_envs:
            _object_name("InfraEnv", infra_env)
        if namespace:
            _object_name("namespace", namespace)
        if not infra_envs:
            return []
        path = (
            f"{_AGENT_INSTALL}/namespaces/{namespace}/agents"
            if namespace
            else (f"{_AGENT_INSTALL}/agents")
        )
        selector = f"{INFRA_ENV_LABEL} in ({','.join(sorted(set(infra_envs)))})"
        pages = await self._paged(
            mce,
            path,
            HubOperation.LIST_AGENTS,
            params={"labelSelector": selector},
            accept=None,
            parse=_agents,
        )
        return sorted((agent for page in pages for agent in page), key=lambda a: a.name)

    async def pods_per_node(self, mce: str) -> dict[str, int]:
        """See HubApi.pods_per_node: Table rows of the non-terminal pods, a page at a time."""
        pages = await self._paged(
            mce,
            f"{_CORE}/pods",
            HubOperation.LIST_PODS,
            params={"fieldSelector": NON_TERMINAL_PODS, "includeObject": "None"},
            accept=TABLE,
            parse=pods_per_node_from,
        )
        counts: dict[str, int] = {}
        for page in pages:
            for node, count in page.items():
                counts[node] = counts.get(node, 0) + count
        return counts

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
            pools = [node_pool_from(item) for item in list_items(raw)]
        except (KeyError, TypeError, ValueError) as exc:
            raise HubUnavailableError(
                f"MCE {mce!r} returned a malformed NodePool list in {namespace}"
            ) from exc
        return sorted(pools, key=lambda pool: pool.name)

    async def _infra_envs(self, mce: str, namespace: str | None) -> list[InfraEnvObservation]:
        if namespace is None:
            path = f"{_AGENT_INSTALL}/infraenvs"
        else:
            _object_name("namespace", namespace)
            path = f"{_AGENT_INSTALL}/namespaces/{namespace}/infraenvs"
        raw = await self._get(mce, path)
        try:
            found = [infra_env_from(item) for item in list_items(raw)]
        except (KeyError, TypeError, ValueError) as exc:
            raise HubUnavailableError(f"MCE {mce!r} returned a malformed InfraEnv list") from exc
        return sorted(found, key=lambda infra_env: infra_env.name)

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
            parsed = [parse(item) for item in list_items(raw)]
        except (KeyError, TypeError, ValueError) as exc:
            raise HubUnavailableError(
                f"MCE {mce!r} returned a malformed list on GET {path}"
            ) from exc
        return sorted(parsed, key=lambda item: item.name)

    async def _paged[T](
        self,
        mce: str,
        path: str,
        operation: HubOperation,
        *,
        params: Mapping[str, str],
        accept: str | None,
        parse: Callable[[JSON], T],
    ) -> list[T]:
        """Every page of a cluster-wide list, each parsed; each page is one observed call.

        A 404 means the hub does not serve the list at all, which is the
        hub's fault. A list still paging after ``MAX_PAGES`` is refused.
        """
        pages: list[T] = []
        token: str | None = None
        for _ in range(MAX_PAGES):
            query = {**params, "limit": str(PAGE_SIZE)}
            if token:
                query["continue"] = token
            page, token = await self._observer.call(
                operation, self._page(mce, path, query, accept, parse)
            )
            pages.append(page)
            if not token:
                return pages
        raise HubUnavailableError(
            f"MCE {mce!r} was still paging GET {path} after {MAX_PAGES} pages of {PAGE_SIZE}"
        )

    async def _page[T](
        self,
        mce: str,
        path: str,
        query: Mapping[str, str],
        accept: str | None,
        parse: Callable[[JSON], T],
    ) -> tuple[T, str | None]:
        try:
            raw = await self._get(mce, path, params=query, accept=accept)
        except HubObjectNotFoundError as exc:
            raise HubUnavailableError(f"MCE {mce!r} does not serve GET {path} (404)") from exc
        try:
            return parse(raw), continue_token(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise HubUnavailableError(
                f"MCE {mce!r} returned a malformed page on GET {path}: {exc}"
            ) from exc

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

    async def _get(
        self,
        mce: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        accept: str | None = None,
    ) -> JSON:
        client = self._client(mce)
        try:
            response = await client.get(
                path, params=params, headers={"Accept": accept} if accept else None
            )
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


def _nodes(raw: JSON) -> list[NodeObservation]:
    return [node_from(item) for item in list_items(raw)]


def _agents(raw: JSON) -> list[AgentObservation]:
    return [agent_from(item) for item in list_items(raw)]
