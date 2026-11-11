"""Every cache key day1 uses, one function per key family (ADR-0011).

Reads build keys here and writes invalidate through the prefixes here, so a
key and the invalidation that clears it cannot drift apart (the legacy
service cleared ``approvals:day1:list`` while the list lived under
``approvals:combined:list``). ``repo`` is the short repository key
(``day1`` or ``specs``).

Families:

- ``<repo>:project``                       the project and its default branch
- ``<repo>:files:...``                     trees, files, history at the default branch
- ``<repo>:commit:<sha>``                  one commit (immutable)
- ``<repo>:mrs:...``                       merge-request lists
- ``day2:installed:<site>:<mce>:<name>``  day2's installed addons for one cluster
- ``hub:<mce>:<kind>:<namespace>[:<name>]`` an MCE hub read for the nodes view
- ``server-scan:rows``                     server-scan's whole fleet, as rows
- ``workflows:uninstall:...``              the orchestrator's uninstall runs: the list, one run
"""

from __future__ import annotations

from collections.abc import Sequence

from wingman_core.domain.git import RepoPath
from wingman_core.domain.merge_request import MRState


def project(repo: str) -> str:
    """The project and its default branch."""
    return f"{repo}:project"


def files_prefix(repo: str) -> str:
    """Everything read from the default branch's tree; cleared when the branch moves."""
    return f"{repo}:files:"


def history(repo: str, path: RepoPath, *, limit: int) -> str:
    """The commits that changed a path."""
    return f"{files_prefix(repo)}history:{limit}:{path}"


def commits(repo: str, *, limit: int) -> str:
    """The newest commits on the default branch."""
    return f"{files_prefix(repo)}commits:{limit}"


def commit(repo: str, sha: str) -> str:
    """One commit; commits never change, so nothing invalidates this family."""
    return f"{repo}:commit:{sha}"


def commit_diff(repo: str, sha: str) -> str:
    """One commit's diff; immutable like the commit."""
    return f"{repo}:commit-diff:{sha}"


def day2_installed(site: str, mce: str, cluster: str) -> str:
    """What day2 reports as installed on one cluster (expires; day2 has no webhook to day1)."""
    return f"day2:installed:{site}:{mce}:{cluster}"


def hub(mce: str, kind: str, namespace: str, name: str | None = None) -> str:
    """One MCE hub read for the nodes view: a list in a namespace, or one object."""
    return f"hub:{mce}:{kind}:{namespace}" + (f":{name}" if name else "")


def server_scan_rows() -> str:
    """server-scan's fleet rows (expires; server-scan has no webhook to day1)."""
    return "server-scan:rows"


def uninstall_runs_prefix() -> str:
    """Every cached uninstall read; cleared when day1 starts one."""
    return "workflows:uninstall:"


def uninstall_runs() -> str:
    """The newest uninstall runs of the fleet."""
    return f"{uninstall_runs_prefix()}runs"


def uninstall_run(workflow_id: str) -> str:
    """One uninstall run's status, step and error."""
    return f"{uninstall_runs_prefix()}run:{workflow_id}"


def merge_requests_prefix(repo: str) -> str:
    """Every merge-request list; cleared when an MR is opened, updated, merged or closed."""
    return f"{repo}:mrs:"


def merge_requests(repo: str, *, state: MRState | None, labels: Sequence[str], limit: int) -> str:
    """One merge-request list."""
    return f"{merge_requests_prefix(repo)}{state or 'any'}:{','.join(sorted(labels))}:{limit}"
