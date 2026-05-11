"""
Live cluster status checker — reads HostedCluster and NodePool conditions
from MCE OpenShift clusters via the Kubernetes API using SA tokens.

Only active when CLUSTER_STATUS_ENABLED=true. Cannot run on minikube.

Script reviewed and rewritten from the original check_cluster.py prototype:
  - Per-MCE token auth replaces load_kube_config() (no kubeconfig on the pod)
  - Returns structured Pydantic models instead of printing
  - Synchronous kubernetes client wrapped for async safety via asyncio.to_thread
  - HC namespace derived from cluster name: hcp-{name without prefix}
  - Timeout enforced on every API call
"""

from __future__ import annotations

import logging
from typing import Any

from wingman_shared.models import ClusterLiveStatus, NodePoolStatus

logger = logging.getLogger(__name__)

HC_GROUP = "hypershift.openshift.io"
HC_VERSION = "v1beta1"
HC_PLURAL = "hostedclusters"
NP_PLURAL = "nodepools"

# HostedCluster: True status means healthy
HC_TRUE_CONDITIONS = {"Available"}
# HostedCluster: True status means a problem
HC_FALSE_CONDITIONS = {"Degraded", "Progressing"}

# NodePool: True status means healthy
NP_TRUE_CONDITIONS = {"Ready"}
# NodePool: True status means a problem
NP_FALSE_CONDITIONS = {"UpdatingVersion", "UpdatingConfig"}

_K8S_TIMEOUT = 10  # seconds per API call


def _get_condition(conditions: list[dict[str, Any]], cond_type: str) -> dict[str, Any] | None:
    return next((c for c in conditions if c.get("type") == cond_type), None)


def _evaluate_conditions(
    conditions: list[dict[str, Any]],
    true_conditions: set[str],
    false_conditions: set[str],
) -> list[str]:
    """Return human-readable problem strings; empty list = all healthy."""
    problems: list[str] = []

    for ctype in true_conditions:
        c = _get_condition(conditions, ctype)
        if c is None:
            problems.append(f"{ctype}: condition not found")
        elif c.get("status") != "True":
            reason = c.get("reason", "")
            msg = c.get("message", "")
            problems.append(f"{ctype}=False  reason={reason}  msg={msg}")

    for ctype in false_conditions:
        c = _get_condition(conditions, ctype)
        if c and c.get("status") == "True":
            reason = c.get("reason", "")
            msg = c.get("message", "")
            problems.append(f"{ctype}=True  reason={reason}  msg={msg}")

    return problems


class ClusterStatusService:
    """
    Checks live HostedCluster + NodePool status by querying MCE OpenShift clusters.

    Each MCE has its own API server and SA token. Tokens are loaded once at
    service construction from the mounted secret file.
    """

    def __init__(
        self,
        mce_tokens: dict[str, str],
        mce_api_domain: str,
        ssl_verify: bool | str = False,
        cluster_name_prefix: str = "ocp4-",
    ) -> None:
        self._tokens = mce_tokens
        self._domain = mce_api_domain
        self._ssl_verify = ssl_verify
        self._cluster_name_prefix = cluster_name_prefix

    def _hc_namespace(self, cluster_name: str) -> str:
        """
        Derive the namespace that contains the HostedCluster CR and its NodePools.
        HC CR name  = full cluster name (e.g. ocp4-prod-web)
        Namespace   = hcp-{cluster name without prefix} (e.g. hcp-prod-web)
        """
        return f"hcp-{cluster_name.removeprefix(self._cluster_name_prefix)}"

    def _build_crd_api(self, mce: str):  # type: ignore[return]
        """
        Build a CustomObjectsApi client authenticating against the given MCE.

        Raises ValueError if no token is configured for the MCE.
        Raises RuntimeError if the kubernetes package is not installed.
        """
        try:
            from kubernetes import client as k8s_client  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "The 'kubernetes' package is required for live cluster status"
            ) from exc

        available_keys = list(self._tokens.keys())
        token = self._tokens.get(mce)
        if not token:
            raise ValueError(
                f"No SA token configured for MCE '{mce}'. "
                f"Available token keys: {available_keys or ['(none)']}"
            )

        api_server = (
            f"https://api.{mce}.{self._domain}:6443" if self._domain else f"https://api.{mce}:6443"
        )
        logger.info("Connecting to MCE '%s' at %s (token key: '%s')", mce, api_server, mce)

        cfg = k8s_client.Configuration()
        cfg.host = api_server
        cfg.api_key_prefix["authorization"] = "Bearer"
        cfg.api_key["authorization"] = token
        cfg.verify_ssl = self._ssl_verify

        api_client = k8s_client.ApiClient(configuration=cfg)
        return k8s_client.CustomObjectsApi(api_client=api_client), api_server

    def fetch_cluster_status(self, cluster_name: str, mce: str) -> ClusterLiveStatus:
        """
        Synchronous status fetch — run via asyncio.to_thread from route handlers.

        Returns a ClusterLiveStatus with error set if the MCE API is unreachable.
        """
        try:
            from kubernetes.client.exceptions import ApiException  # noqa: PLC0415
        except ImportError:
            ApiException = Exception  # type: ignore[assignment,misc]

        try:
            crd, api_server = self._build_crd_api(mce)
        except (ValueError, RuntimeError) as exc:
            return ClusterLiveStatus(cluster_name=cluster_name, error=str(exc))

        hc_namespace = self._hc_namespace(cluster_name)

        def _api_error(exc: Exception) -> str:
            status_code = getattr(exc, "status", None)
            if status_code == 401:
                return (
                    f"Authentication failed (401 Unauthorized): the SA token for MCE '{mce}' "
                    f"was rejected by {api_server}. "
                    "Check that the token in the secrets file is valid and not expired."
                )
            if status_code == 403:
                return (
                    f"Authorization failed (403 Forbidden): the SA token for MCE '{mce}' "
                    f"does not have permission to read HostedCluster resources in "
                    f"namespace '{hc_namespace}' on {api_server}."
                )
            if status_code == 404:
                return (
                    f"HostedCluster '{cluster_name}' not found in namespace '{hc_namespace}' "
                    f"on MCE '{mce}' ({api_server})."
                )
            return f"API error from {api_server}: {exc}"

        # ── HostedCluster ──────────────────────────────────────────────────────
        try:
            hc = crd.get_namespaced_custom_object(
                group=HC_GROUP,
                version=HC_VERSION,
                namespace=hc_namespace,
                plural=HC_PLURAL,
                name=cluster_name,
                _request_timeout=_K8S_TIMEOUT,
            )
        except ApiException as exc:
            msg = _api_error(exc)
            logger.warning("HostedCluster fetch failed for %s/%s: %s", mce, cluster_name, msg)
            return ClusterLiveStatus(cluster_name=cluster_name, error=msg)
        except Exception as exc:
            logger.warning(
                "Failed to fetch HostedCluster %s from MCE %s (%s): %s",
                cluster_name,
                mce,
                api_server,
                exc,
            )
            return ClusterLiveStatus(
                cluster_name=cluster_name,
                error=f"Failed to connect to MCE '{mce}' at {api_server}: {exc}",
            )

        hc_conditions: list[dict[str, Any]] = hc.get("status", {}).get("conditions", [])
        hc_problems = _evaluate_conditions(hc_conditions, HC_TRUE_CONDITIONS, HC_FALSE_CONDITIONS)

        # ── NodePools ──────────────────────────────────────────────────────────
        node_pools: list[NodePoolStatus] = []

        try:
            np_list = crd.list_namespaced_custom_object(
                group=HC_GROUP,
                version=HC_VERSION,
                namespace=hc_namespace,
                plural=NP_PLURAL,
                _request_timeout=_K8S_TIMEOUT,
            )
            for np in np_list.get("items", []):
                np_name = np["metadata"]["name"]
                np_conditions: list[dict[str, Any]] = np.get("status", {}).get("conditions", [])
                np_status = np.get("status", {})
                np_spec = np.get("spec", {})
                # HyperShift NodePool: spec.replicas = desired, status.replicas = current observed.
                # status.readyReplicas does not exist in HyperShift — use status.replicas.
                desired = int(np_spec.get("replicas", np_status.get("replicas", 0)))
                current = int(np_status.get("replicas", 0))
                logger.debug(
                    "NodePool %s: spec.replicas=%s status.replicas=%s status keys=%s",
                    np_name,
                    np_spec.get("replicas"),
                    np_status.get("replicas"),
                    list(np_status.keys()),
                )
                node_pools.append(
                    NodePoolStatus(
                        name=np_name,
                        ready_replicas=current,
                        desired_replicas=desired,
                        problems=_evaluate_conditions(
                            np_conditions, NP_TRUE_CONDITIONS, NP_FALSE_CONDITIONS
                        ),
                    )
                )
        except ApiException as exc:
            msg = _api_error(exc)
            logger.warning("NodePool fetch failed for %s/%s: %s", mce, cluster_name, msg)
            hc_problems.append(f"NodePool fetch failed: {msg}")
        except Exception as exc:
            logger.warning("Failed to fetch NodePools for %s: %s", cluster_name, exc)
            hc_problems.append(f"NodePool fetch failed: {exc}")

        hc_status = hc.get("status", {})
        hc_phase: str | None = hc_status.get("phase")
        ocp_version: str | None = None
        try:
            history = hc_status.get("version", {}).get("history", [])
            if history:
                ocp_version = history[0].get("version")
        except Exception:
            pass

        return ClusterLiveStatus(
            cluster_name=cluster_name,
            hc_problems=hc_problems,
            node_pools=node_pools,
            hc_phase=hc_phase,
            ocp_version=ocp_version,
        )
