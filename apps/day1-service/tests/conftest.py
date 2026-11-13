"""Shared fixtures: the whole day1 service on an in-memory GitLab seeded from dev/gitlab-fixtures.

Nothing here talks to a network. ``world`` is the seeded fake plus the fake
hub, identity provider and day2; ``app`` is ``create_app`` on top of them,
exactly as production wires it except for the adapters; ``client`` speaks
HTTP to it through ``httpx.ASGITransport``.
"""

from __future__ import annotations

import itertools
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.domain.merge_request import MergeRequest, NewMergeRequest
from wingman_core.domain.users import Role, User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.infrastructure.session_tokens import SessionTokens
from wingman_core.settings import AuthSettings, Environment, GitBackend, RuntimeSettings
from wingman_core.testing.fixtures import default_fixture_root, load_fixture_projects, seed_fake
from wingman_day1.api.deps import Day1Context
from wingman_day1.domain.addons import InstalledAddon
from wingman_day1.domain.auth import Identity
from wingman_day1.domain.mce_capacity import NodeObservation
from wingman_day1.domain.status import Condition, HostedClusterObservation, NodePoolObservation
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_identity import FakeIdentityProvider
from wingman_day1.main import Adapters, create_app
from wingman_day1.ports import (
    AddServerWorkflow,
    HubApi,
    ProvisionWorkflow,
    SegmentLedger,
    ServerInventory,
    UninstallWorkflow,
    UpgradeWorkflow,
)
from wingman_day1.settings import Day1Settings

DAY1 = "gitops-day1/platform-config"
SPECS = "wingman/cluster-specs"
JWT_SECRET = "test-jwt-secret-of-at-least-32-characters"
DEV_SECRET = "test-dev-secret-of-at-least-32-characters"

ALICE = User(username="alice", role=Role.ADMIN, groups=("admins",), full_name="Alice Admin")
BOB = User(username="bob", role=Role.ADMIN, groups=("admins",), full_name="Bob Admin")
VIEWER = User(username="vera", role=Role.VIEWER, groups=("viewers",))

PROD_MCE = "ocp4-prod-mce-site1-a"
FIXTURE_MCES = (
    "ocp4-mce-workflow-test",
    "ocp4-prep-mce-site1-a",
    PROD_MCE,
    "ocp4-prep-mce-site2-a",
    "ocp4-prod-mce-site2-a",
)
"""Every MCE folder of dev/gitlab-fixtures that the shared hub serves."""
ROOMY = (
    NodeObservation("master-0", True, False, True, 250),
    NodeObservation("worker-0", True, False, False, 250),
    NodeObservation("worker-1", True, False, False, 250),
)
"""A hub with room for a control plane: 500 allocatable pods on its two workers."""
PROD_SITE = "site1"


class StepClock:
    """A clock that moves one second per call, so branch names never collide."""

    def __init__(self, start: datetime = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)) -> None:
        self._ticks = itertools.count()
        self._start = start

    def __call__(self) -> datetime:
        return self._start + timedelta(seconds=next(self._ticks))


def nodepools(*infra_envs: str, replicas: int = 2) -> list[dict[str, object]]:
    """Form-shaped nodepool inputs for the fixture template."""
    return [
        {
            "infra_env": env,
            "replicas": replicas,
            "configs": [{"name": "worker-kubeletconfig-reserved"}],
        }
        for env in infra_envs
    ]


def create_body(name: str = "ocp4-prod-falcon-site1", **overrides: object) -> dict[str, object]:
    """A valid create request for agent-standard v1.0.0 under the prod MCE."""
    body: dict[str, object] = {
        "name": name,
        "site": PROD_SITE,
        "mce": PROD_MCE,
        "spec_name": "agent-standard",
        "spec_version": "1.0.0",
        "variables": {
            "owner_merkaz": "1234",
            "owner_anaf": "56",
            "owner_mador": "7",
            "openshift_release_version": "4.18.56-x86_64",
            "nodepools": nodepools("dell-r660-site1-128c-1024gb-5tb", "hp-gen11-site1-64c"),
        },
    }
    body.update(overrides)
    return body


def seeded(clock: StepClock) -> InMemoryGitLab:
    """A fresh in-memory GitLab holding every fixture project."""
    gitlab = InMemoryGitLab(clock=clock)
    seed_fake(gitlab, load_fixture_projects(default_fixture_root()))
    return gitlab


@pytest.fixture
def clock() -> StepClock:
    return StepClock()


@pytest.fixture
def gitlab(clock: StepClock) -> InMemoryGitLab:
    return seeded(clock)


@pytest.fixture
def hub() -> FakeHubApi:
    healthy = (
        Condition("Available", "True"),
        Condition("Degraded", "False"),
        Condition("Progressing", "False"),
    )
    return FakeHubApi(
        hosted_clusters={
            PROD_MCE: [
                HostedClusterObservation(
                    name="ocp4-prod-herzi-site1",
                    namespace="hcp-prod-herzi-site1",
                    phase=None,
                    version="4.16.27",
                    conditions=healthy,
                )
            ]
        },
        node_pools={
            (PROD_MCE, "hcp-prod-herzi-site1"): [
                NodePoolObservation(
                    name="prod-herzi-site1-dell",
                    desired_replicas=2,
                    current_replicas=2,
                    conditions=(Condition("Ready", "True"),),
                )
            ]
        },
        infra_envs={PROD_MCE: {"inventory": ["dell-r660-site1-128c-1024gb-5tb"]}},
        # Each fixture site has one MCE per env, so with room on every hub the
        # MCE a test creates on is placement's pick (ADR-0050)
        nodes=dict.fromkeys(FIXTURE_MCES, ROOMY),
        pods={mce: {"master-0": 120, "worker-0": 100, "worker-1": 90} for mce in FIXTURE_MCES},
        free_of_any_type=dict.fromkeys(FIXTURE_MCES, 8),
    )


@pytest.fixture
def identity() -> FakeIdentityProvider:
    return FakeIdentityProvider(
        {
            "code-admin": Identity("olga", ("admins",), "uid-olga", "Olga Ops"),
            "code-viewer": Identity("vic", ("viewers",), "uid-vic", "Vic Viewer"),
            "code-nobody": Identity("nora", ("other",), "uid-nora", "Nora Nobody"),
        },
        authorize_url="https://oauth.example.invalid/oauth/authorize?client_id=wingman",
    )


@pytest.fixture
def day2() -> FakeDay2Addons:
    return FakeDay2Addons(
        {"ocp4-prod-herzi-site1": [InstalledAddon("redbull", "cluster-roles", "main")]}
    )


def make_settings(**overrides: object) -> Day1Settings:
    values: dict[str, object] = {
        "day1_gitlab_project_id": DAY1,
        "specs_gitlab_project_id": SPECS,
        "dev_auth_enabled": True,
        "dev_auth_secret": SecretStr(DEV_SECRET),
        "gitlab_webhook_secret": SecretStr("test-webhook-secret"),
        "day1_status_poll_seconds": 5.0,
    }
    values.update(overrides)
    return Day1Settings(**values)  # ty: ignore[invalid-argument-type]


def make_auth() -> AuthSettings:
    return AuthSettings(
        jwt_secret_key=SecretStr(JWT_SECRET),
        wingman_admin_groups="admins",
        wingman_viewer_groups="viewers",
    )


def build_app(
    *,
    gitlab: InMemoryGitLab,
    hub: HubApi | None,
    identity: FakeIdentityProvider | None,
    day2: FakeDay2Addons,
    clock: StepClock,
    inventory: ServerInventory | None = None,
    uninstall: UninstallWorkflow | None = None,
    ledger: SegmentLedger | None = None,
    provision: ProvisionWorkflow | None = None,
    upgrade: UpgradeWorkflow | None = None,
    add_server: AddServerWorkflow | None = None,
    **settings: object,
) -> FastAPI:
    return create_app(
        settings=make_settings(**settings),
        auth=make_auth(),
        runtime=RuntimeSettings(environment=Environment.TEST, git_backend=GitBackend.FAKE),
        adapters=Adapters(
            gitlab=gitlab,
            day2=day2,
            hub=hub,
            identity=identity,
            inventory=inventory,
            uninstall=uninstall,
            ledger=ledger,
            provision=provision,
            upgrade=upgrade,
            day2_installs=day2,
            add_server=add_server,
        ),
        clock=clock,
    )


@pytest.fixture
def app(
    gitlab: InMemoryGitLab,
    hub: FakeHubApi,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: StepClock,
) -> FastAPI:
    return build_app(gitlab=gitlab, hub=hub, identity=identity, day2=day2, clock=clock)


@pytest.fixture
def context(app: FastAPI) -> Day1Context:
    return app.state.day1


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as c:
        yield c


@pytest.fixture
def token(app: FastAPI) -> Callable[[User], str]:
    tokens: SessionTokens = app.state.session_tokens
    return tokens.issue


@pytest.fixture
def auth(token: Callable[[User], str]) -> Callable[[User], dict[str, str]]:
    return lambda user: {"Authorization": f"Bearer {token(user)}"}


async def project_id(gitlab: InMemoryGitLab, path: str) -> int:
    return (await gitlab.get_project(path)).id


async def push(gitlab: InMemoryGitLab, path: str, *, branch: str, file: str, content: str) -> None:
    """Commit as someone else (CI, the workflow, a person) without Wingman knowing."""
    pid = await project_id(gitlab, path)
    try:
        current = await gitlab.read_file(pid, RepoPath(file), branch)
    except NotFoundError:
        change = FileChange.create(RepoPath(file), content)
    else:
        change = FileChange.update(RepoPath(file), content, last_commit_id=current.last_commit_id)
    await gitlab.commit(pid, branch=branch, message="outside push [skip ci]", changes=[change])


async def open_provision_mr(
    gitlab: InMemoryGitLab,
    stem: str,
    *,
    mce: str = PROD_MCE,
    site: str = PROD_SITE,
    mador: str = "7",
    branch: str | None = None,
    title: str | None = None,
    labels: tuple[str, ...] = (),
) -> MergeRequest:
    """An MR as the provision-cluster workflow opens it (ADR-0042): its branch and title, no label.

    It adds ``<stem>.yaml`` under ``site``/``mce`` with the allocation, on
    ``provision-cluster/<stem>`` unless ``branch`` names another.
    """
    branch = branch or f"provision-cluster/{stem}"
    pid = await project_id(gitlab, DAY1)
    await gitlab.create_branch(pid, branch, "main")
    content = (
        f'owner:\n  merkaz: "1234"\n  anaf: "56"\n  mador: "{mador}"\n'
        "mastertag: 4.18.56-x86_64\nvlanId: 1234\n"
    )
    file = f"sites/{site}/mces/{mce}/hostedClusters/{stem}.yaml"
    await push(gitlab, DAY1, branch=branch, file=file, content=content)
    return await gitlab.create_merge_request(
        pid,
        NewMergeRequest(
            source_branch=branch,
            target_branch="main",
            title=title or f"Provision hosted cluster {stem} on {mce}",
            labels=labels,
        ),
    )


class Support:
    """Helpers for tests, as one fixture (``--import-mode=importlib`` cannot import conftest)."""

    DAY1 = DAY1
    SPECS = SPECS
    DEV_SECRET = DEV_SECRET
    ALICE = ALICE
    BOB = BOB
    VIEWER = VIEWER
    PROD_MCE = PROD_MCE
    PROD_SITE = PROD_SITE

    create_body = staticmethod(create_body)
    nodepools = staticmethod(nodepools)
    make_settings = staticmethod(make_settings)
    make_auth = staticmethod(make_auth)
    build_app = staticmethod(build_app)
    seeded = staticmethod(seeded)
    project_id = staticmethod(project_id)
    push = staticmethod(push)
    open_provision_mr = staticmethod(open_provision_mr)


@pytest.fixture
def support() -> type[Support]:
    return Support
