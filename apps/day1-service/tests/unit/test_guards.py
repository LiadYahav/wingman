"""Regression guards for legacy bugs that must not come back.

- The legacy service called python-gitlab synchronously on the event loop
  (health checks timed out). wingman_day1 reaches GitLab only through the
  async ``GitLabPort``: no module may import python-gitlab, the legacy
  ``wingman_shared`` client, or the sync ``kubernetes`` client.
- The legacy MCE-create path wrote ``hostedClusters/.gitkeep``, which breaks
  the MCE's ApplicationSet, and read ``<cluster>.wingman.yaml`` sidecars from
  the same folder. Every change the provisioner makes is exactly the cluster
  file.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from pathlib import Path

import pytest

from wingman_core.domain.git import FileChange
from wingman_core.domain.merge_request import MergeRequest
from wingman_core.domain.mr_conventions import ResourceType, Verb
from wingman_core.domain.users import Role, User
from wingman_day1.domain.changes import ClusterAction, ClusterChange
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.infrastructure.merge_requests import GitClusterProvisioner, MergeRequestWriter

SOURCE = Path(__file__).resolve().parents[2] / "src" / "wingman_day1"
FORBIDDEN_IMPORTS = ("gitlab", "wingman_shared", "kubernetes")
ALICE = User(username="alice", role=Role.ADMIN)
REF = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-falcon-site1")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def test_the_source_tree_is_where_the_guards_look() -> None:
    assert (SOURCE / "main.py").is_file()
    assert len(list(SOURCE.rglob("*.py"))) > 20


@pytest.mark.parametrize("path", sorted(SOURCE.rglob("*.py")), ids=lambda p: p.name)
def test_no_module_imports_a_sync_or_legacy_client(path: Path) -> None:
    offending = sorted(
        module for module in _imported_modules(path) if module.split(".")[0] in FORBIDDEN_IMPORTS
    )
    assert offending == [], f"{path.relative_to(SOURCE)} imports {offending}"


@pytest.mark.parametrize("path", sorted(SOURCE.rglob("*.py")), ids=lambda p: p.name)
def test_no_module_names_a_placeholder_or_sidecar_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    code = ast.unparse(ast.parse(text))  # without comments, so docs may explain the history
    strings = [
        node.value
        for node in ast.walk(ast.parse(code))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(ast.parse(code))
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    }
    literals = [s for s in strings if s not in docstrings]
    assert not [s for s in literals if ".gitkeep" in s or ".wingman.yaml" in s]


class RecordingWriter(MergeRequestWriter):
    """A writer that records what it would commit instead of committing."""

    def __init__(self) -> None:
        self.changes: list[FileChange] = []

    async def open(
        self,
        *,
        requested_by: User,
        verb: Verb,
        resource_type: ResourceType,
        resource_name: str,
        action: str,
        changes: Sequence[FileChange],
        summary: str,
        commit_message: str,
        title_extra: str = "",
    ) -> MergeRequest:
        self.changes.extend(changes)
        raise _Recorded


class _Recorded(Exception):
    pass


@pytest.mark.parametrize(
    "change",
    [
        ClusterChange(ClusterAction.CREATE, REF, ALICE, "s", content="mastertag: 4.18.22\n"),
        ClusterChange(
            ClusterAction.MODIFY, REF, ALICE, "s", content="a: 1\n", last_commit_id="a" * 8
        ),
        ClusterChange(ClusterAction.DELETE, REF, ALICE, "s", last_commit_id="a" * 8),
        ClusterChange(
            ClusterAction.SYNC, REF, ALICE, "s", content="a: 1\n", last_commit_id="a" * 8
        ),
        ClusterChange(
            ClusterAction.IMPORT,
            REF,
            ALICE,
            "s",
            content="a: 1\n",
            last_commit_id="a" * 8,
            spec_name="agent-baseline",
            spec_version="1.0.0",
        ),
    ],
    ids=lambda c: str(c.action),
)
async def test_every_provisioned_change_touches_exactly_the_cluster_file(
    change: ClusterChange,
) -> None:
    writer = RecordingWriter()
    with pytest.raises(_Recorded):
        await GitClusterProvisioner(writer).apply(change)
    assert [str(c.path) for c in writer.changes] == [str(REF.path)]
    assert REF.path.parent.name == "hostedClusters"
    assert REF.path.name == f"{REF.name}.yaml"
