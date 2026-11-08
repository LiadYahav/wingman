"""The merge-request writer and the Git provisioners: one commit, one file, one MR, the contract."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from wingman_core.domain.errors import RevisionConflictError
from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.domain.merge_request import MRState
from wingman_core.domain.mr_conventions import (
    Repo,
    ResourceType,
    Verb,
    parse_mr_description,
    parse_mr_title,
)
from wingman_core.domain.users import Role, User
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.testing.fixtures import default_fixture_root, load_fixture_projects, seed_fake
from wingman_day1.domain.changes import (
    ClusterAction,
    ClusterChange,
    FileUpdate,
    ImportChange,
    SpecAction,
    SpecChange,
)
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.infrastructure.merge_requests import (
    GitClusterProvisioner,
    GitSpecChanges,
    MergeRequestWriter,
)
from wingman_day1.infrastructure.repositories import CachedRepository

DAY1 = "gitops-day1/platform-config"
SPECS = "wingman/cluster-specs"
NOW = datetime(2026, 11, 7, 14, 30, 22, tzinfo=UTC)
ALICE = User(username="alice", role=Role.ADMIN, full_name="Alice Admin")
NEW = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-falcon-site1")
HERZI = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-herzi-site1")
CONTENT = "mastertag: 4.18.22\nnodepool:\n  - infraEnvName: pool\n"


def clock() -> datetime:
    return NOW


@pytest.fixture
def gitlab() -> InMemoryGitLab:
    gitlab = InMemoryGitLab()
    seed_fake(gitlab, load_fixture_projects(default_fixture_root()))
    return gitlab


@pytest.fixture
def day1(gitlab: InMemoryGitLab) -> CachedRepository:
    return CachedRepository(gitlab, TtlCache(), key="day1", project=DAY1, ttl=30)


@pytest.fixture
def provisioner(gitlab: InMemoryGitLab, day1: CachedRepository) -> GitClusterProvisioner:
    return GitClusterProvisioner(
        MergeRequestWriter(gitlab, day1, repo=Repo.DAY1, label="day1", clock=clock)
    )


def create(ref: ClusterRef = NEW) -> ClusterChange:
    return ClusterChange(
        ClusterAction.CREATE,
        ref,
        ALICE,
        "Creating it.",
        content=CONTENT,
        spec_name="agent-standard",
        spec_version="1.0.0",
    )


async def test_a_create_is_one_commit_adding_exactly_the_cluster_file(
    gitlab: InMemoryGitLab, provisioner: GitClusterProvisioner
) -> None:
    project = await gitlab.get_project(DAY1)
    main_before = gitlab.snapshot(project.id, "main")
    mr = (await provisioner.apply(create())).merge_request
    branch = gitlab.snapshot(project.id, mr.source_branch)
    assert {p: c for p, c in branch.items() if p != str(NEW.path)} == main_before
    assert branch[str(NEW.path)] == CONTENT
    assert gitlab.snapshot(project.id, "main") == main_before
    head = (await gitlab.list_commits(project.id, ref=mr.source_branch, limit=1))[0]
    main_head = (await gitlab.list_commits(project.id, ref="main", limit=1))[0]
    assert head.parent_ids == (main_head.id,)
    diff = await gitlab.commit_diff(project.id, head.id)
    assert [(str(d.new_path), d.new_file) for d in diff] == [(str(NEW.path), True)]


async def test_the_mr_follows_the_conventions_and_parses_back(
    gitlab: InMemoryGitLab, provisioner: GitClusterProvisioner
) -> None:
    mr = (await provisioner.apply(create())).merge_request
    assert (
        mr.source_branch == "platform/alice/create-cluster-ocp4-prod-falcon-site1-20261107T143022"
    )
    assert mr.target_branch == "main"
    assert (
        mr.title == "[Wingman/Day1] Create cluster ocp4-prod-falcon-site1 from spec agent-standard"
    )
    title = parse_mr_title(mr.title)
    assert title is not None
    assert (title.repo, title.verb, title.resource_type, title.resource_name) == (
        Repo.DAY1,
        Verb.CREATE,
        ResourceType.CLUSTER,
        NEW.name,
    )
    footer = parse_mr_description(mr.description)
    assert footer is not None
    assert (footer.author, footer.action, footer.resource_name, footer.repo) == (
        "alice",
        "create",
        NEW.name,
        Repo.DAY1,
    )
    assert mr.description.startswith("Creating it.")
    assert mr.labels == ("create", "day1", "wingman")
    assert mr.state is MRState.OPENED


async def test_the_commit_is_authored_by_the_requesting_user(
    gitlab: InMemoryGitLab, provisioner: GitClusterProvisioner
) -> None:
    project = await gitlab.get_project(DAY1)
    mr = (await provisioner.apply(create())).merge_request
    head = (await gitlab.list_commits(project.id, ref=mr.source_branch, limit=1))[0]
    assert (head.author_name, head.author_email) == ("Alice Admin", "alice@openshift.local")
    assert head.title == "Create cluster ocp4-prod-falcon-site1 from spec agent-standard"
    assert "Site: site1, MCE: ocp4-prod-mce-site1-a" in head.message
    assert "Spec: agent-standard v1.0.0" in head.message
    assert head.message.endswith("Requested-by: alice")


async def test_a_modify_carries_the_revision_it_was_read_at(
    gitlab: InMemoryGitLab, provisioner: GitClusterProvisioner
) -> None:
    project = await gitlab.get_project(DAY1)
    current = await gitlab.read_file(project.id, HERZI.path, "main")
    change = ClusterChange(
        ClusterAction.MODIFY,
        HERZI,
        ALICE,
        "Bump.",
        content=current.content.replace("4.16.27", "4.16.28"),
        last_commit_id=current.last_commit_id,
    )
    mr = (await provisioner.apply(change)).merge_request
    assert mr.title == "[Wingman/Day1] Modify cluster ocp4-prod-herzi-site1"
    assert mr.labels == ("day1", "modify", "wingman")
    assert "4.16.28" in gitlab.snapshot(project.id, mr.source_branch)[str(HERZI.path)]


async def test_a_modify_from_a_stale_read_is_refused_by_gitlab(
    gitlab: InMemoryGitLab, provisioner: GitClusterProvisioner
) -> None:
    project = await gitlab.get_project(DAY1)
    current = await gitlab.read_file(project.id, HERZI.path, "main")
    await gitlab.commit(
        project.id,
        branch="main",
        message="CI: allocate segment [skip ci]",
        changes=[
            FileChange.update(HERZI.path, current.content + "vlanId: 7\n", last_commit_id=None)
        ],
    )
    stale = ClusterChange(
        ClusterAction.MODIFY,
        HERZI,
        ALICE,
        "Bump.",
        content="mastertag: 4.16.28\n",
        last_commit_id=current.last_commit_id,
    )
    with pytest.raises(RevisionConflictError):
        await provisioner.apply(stale)


async def test_a_delete_removes_only_the_cluster_file(
    gitlab: InMemoryGitLab, provisioner: GitClusterProvisioner
) -> None:
    project = await gitlab.get_project(DAY1)
    current = await gitlab.read_file(project.id, HERZI.path, "main")
    change = ClusterChange(
        ClusterAction.DELETE, HERZI, ALICE, "Bye.", last_commit_id=current.last_commit_id
    )
    mr = (await provisioner.apply(change)).merge_request
    main = gitlab.snapshot(project.id, "main")
    branch = gitlab.snapshot(project.id, mr.source_branch)
    assert set(main) - set(branch) == {str(HERZI.path)}
    assert set(branch) <= set(main)
    assert mr.title == "[Wingman/Day1] Delete cluster ocp4-prod-herzi-site1"


async def test_opening_an_mr_clears_the_cached_mr_lists(
    day1: CachedRepository, provisioner: GitClusterProvisioner
) -> None:
    assert await day1.merge_requests(state=MRState.OPENED, labels=("wingman",)) == []
    mr = (await provisioner.apply(create())).merge_request
    listed = await day1.merge_requests(state=MRState.OPENED, labels=("wingman",))
    assert [m.ref for m in listed] == [mr.ref]


async def test_changes_start_from_the_projects_default_branch_whatever_its_name() -> None:
    gitlab = InMemoryGitLab()
    gitlab.create_project(
        DAY1, {"sites/site1/mces/m/values.yaml": "a: 1\n"}, default_branch="production"
    )
    repo = CachedRepository(gitlab, TtlCache(), key="day1", project=DAY1, ttl=30)
    provisioner = GitClusterProvisioner(
        MergeRequestWriter(gitlab, repo, repo=Repo.DAY1, label="day1", clock=clock)
    )
    mr = (await provisioner.apply(create(ClusterRef("site1", "m", "c")))).merge_request
    assert mr.target_branch == "production"
    project = await gitlab.get_project(DAY1)
    assert "sites/site1/mces/m/values.yaml" in gitlab.snapshot(project.id, mr.source_branch)
    listed = await repo.merge_requests(state=MRState.OPENED, labels=("wingman",))
    assert [m.ref for m in listed] == [mr.ref]


@pytest.fixture
def spec_changes(gitlab: InMemoryGitLab) -> tuple[GitSpecChanges, CachedRepository]:
    specs = CachedRepository(gitlab, TtlCache(), key="specs", project=SPECS, ttl=30)
    writer = MergeRequestWriter(gitlab, specs, repo=Repo.SPECS, label="specs", clock=clock)
    return GitSpecChanges(writer, specs_root="specs"), specs


async def test_spec_changes_open_specs_mrs(
    gitlab: InMemoryGitLab, spec_changes: tuple[GitSpecChanges, CachedRepository]
) -> None:
    changes, specs = spec_changes
    project = await gitlab.get_project(SPECS)
    created = (
        await changes.apply(
            SpecChange(SpecAction.CREATE, "big", "2.0.0", ALICE, "New.", content="x: 1\n")
        )
    ).merge_request
    assert created.title == "[Wingman/Specs] Create spec big"
    assert created.labels == ("create", "specs", "wingman")
    assert gitlab.snapshot(project.id, created.source_branch)["specs/big.yaml"] == "x: 1\n"

    current = await specs.read(RepoPath("specs/agent-single.yaml"))
    updated = (
        await changes.apply(
            SpecChange(
                SpecAction.UPDATE,
                "agent-single",
                "1.1.0",
                ALICE,
                "Bump.",
                content="y: 2\n",
                last_commit_id=current.last_commit_id,
            )
        )
    ).merge_request
    assert updated.title == "[Wingman/Specs] Update spec agent-single to v1.1.0"
    footer = parse_mr_description(updated.description)
    assert footer is not None
    assert (footer.action, footer.resource_type) == ("update", ResourceType.SPEC)

    deleted = (
        await changes.apply(
            SpecChange(
                SpecAction.DELETE,
                "agent-single",
                "1.0.0",
                ALICE,
                "Bye.",
                last_commit_id=current.last_commit_id,
            )
        )
    ).merge_request
    assert deleted.title == "[Wingman/Specs] Delete spec agent-single"
    assert "specs/agent-single.yaml" not in gitlab.snapshot(project.id, deleted.source_branch)
    head = (await gitlab.list_commits(project.id, ref=deleted.source_branch, limit=1))[0]
    assert head.title == "Delete spec agent-single v1.0.0"


# ── Import: several files, one commit, one MR ────────────────────────────────

LARK = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-lark-site1")


async def linking(gitlab: InMemoryGitLab, *refs: ClusterRef, stale: bool = False) -> ImportChange:
    project = await gitlab.get_project(DAY1)
    files = []
    for ref in refs:
        current = await gitlab.read_file(project.id, ref.path, "main")
        files.append(
            FileUpdate(
                ref,
                f'# specName: "agent-baseline"\n{current.content}',
                "0" * 40 if stale else current.last_commit_id,
            )
        )
    return ImportChange("agent-baseline", "1.0.0", tuple(files), ALICE, "Linking.")


async def test_an_import_is_one_commit_changing_exactly_the_picked_files(
    gitlab: InMemoryGitLab, provisioner: GitClusterProvisioner
) -> None:
    project = await gitlab.get_project(DAY1)
    main_before = gitlab.snapshot(project.id, "main")
    mr = (await provisioner.link(await linking(gitlab, HERZI, LARK))).merge_request
    branch = gitlab.snapshot(project.id, mr.source_branch)
    changed = sorted(p for p in branch if branch[p] != main_before.get(p))
    assert changed == sorted([str(HERZI.path), str(LARK.path)])
    assert branch[str(LARK.path)] == '# specName: "agent-baseline"\n' + main_before[str(LARK.path)]
    assert gitlab.snapshot(project.id, "main") == main_before
    head = (await gitlab.list_commits(project.id, ref=mr.source_branch, limit=1))[0]
    assert head.title == "Import 2 clusters into spec agent-baseline v1.0.0"
    assert "- ocp4-prod-lark-site1 (site1/ocp4-prod-mce-site1-a)" in head.message
    assert (head.author_name, head.message.splitlines()[-1]) == (
        "Alice Admin",
        "Requested-by: alice",
    )
    assert mr.title == "[Wingman/Day1] Import spec agent-baseline into 2 clusters"
    assert mr.source_branch == "platform/alice/import-spec-agent-baseline-20261107T143022"
    assert mr.labels == ("day1", "import", "wingman")
    footer = parse_mr_description(mr.description)
    assert footer is not None
    assert (footer.action, footer.resource_type, footer.resource_name) == (
        "import",
        ResourceType.SPEC,
        "agent-baseline",
    )


async def test_an_import_with_one_file_that_moved_commits_nothing(
    gitlab: InMemoryGitLab, provisioner: GitClusterProvisioner
) -> None:
    project = await gitlab.get_project(DAY1)
    fresh = (await linking(gitlab, HERZI)).files[0]
    moved = (await linking(gitlab, LARK, stale=True)).files[0]
    with pytest.raises(RevisionConflictError):
        await provisioner.link(ImportChange("agent-baseline", "1.0.0", (fresh, moved), ALICE, "x"))
    assert await gitlab.list_merge_requests(project.id, state=None) == []
    assert [b.name for b in await gitlab.list_branches(project.id)] == ["main"]


def test_an_import_changes_each_file_once_and_at_least_one() -> None:
    update = FileUpdate(LARK, "x: 1\n", "a" * 8)
    with pytest.raises(ValueError, match="at least one"):
        ImportChange("s", "1", (), ALICE, "x")
    with pytest.raises(ValueError, match="each cluster file once"):
        ImportChange("s", "1", (update, update), ALICE, "x")
    with pytest.raises(ValueError, match="last_commit_id"):
        ImportChange("s", "1", (FileUpdate(LARK, "x", ""),), ALICE, "x")
