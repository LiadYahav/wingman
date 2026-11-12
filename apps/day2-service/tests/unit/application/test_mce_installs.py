"""Deploy an add-on on specific MCEs: one install MR per MCE (ADR-0053's amendment, ADR-0022)."""

from __future__ import annotations

from typing import Any

import pytest

from wingman_core.domain.errors import GitUnavailableError, InvalidRequestError
from wingman_core.domain.git import ChangeKind, FileChange, RepoPath
from wingman_core.domain.mr_conventions import Verb, parse_mr_title
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day2.application.services import Day2Services
from wingman_day2.domain.errors import ChangeRefusedError, TeamReadOnlyError, UnknownChartError
from wingman_day2.domain.platform import AppSource

PREP = "mce:site1:prep:ocp4-prep-mce-site1-a"
PROD = "mce:site1:prod:ocp4-prod-mce-site1-a"
PREP_DIR = "sites/site1/prep/mces/ocp4-prep-mce-site1-a/in-cluster"
PROD_DIR = "sites/site1/prod/mces/ocp4-prod-mce-site1-a/in-cluster"


async def test_each_chosen_mce_gets_its_own_install_mr(
    services: Day2Services, jane_user: User, bob_user: User
) -> None:
    result = await services.changes.install_on_mces(
        "redbull", "cluster-roles", [PREP, PROD], jane_user, values={"tier": "hub"}
    )
    assert [(i.cluster.id, i.status) for i in result.installs] == [
        (PREP, "opened"),
        (PROD, "opened"),
    ]
    prep, prod = result.installs
    assert [(c.kind, str(c.path)) for c in prep.changes] == [
        (ChangeKind.CREATE, f"{PREP_DIR}/cluster-roles/values.yaml")
    ]
    assert [str(c.path) for c in prod.changes] == [f"{PROD_DIR}/cluster-roles/values.yaml"]
    assert prep.result is not None and prod.result is not None
    mr = prep.result.merge_request
    assert mr.title == "[Wingman/Day2] Install addon redbull/cluster-roles on ocp4-prep-mce-site1-a"
    title = parse_mr_title(mr.title)
    assert title is not None and title.verb is Verb.INSTALL
    assert prep.result.merge_request.ref.iid != prod.result.merge_request.ref.iid
    for install in result.installs:
        assert install.result is not None
        mr = install.result.merge_request
        await services.approvals.approve("redbull", mr.ref.iid, sha=mr.sha, approver=bob_user)
    after = (await services.topology.load()).team("redbull").plan
    apps = {a.ref.id: a.source for a in after.apps if a.chart == "cluster-roles"}
    assert apps[PREP] is AppSource.CLUSTER and apps[PROD] is AppSource.CLUSTER


async def test_a_dry_run_plans_each_mce_and_opens_nothing(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    result = await services.changes.install_on_mces(
        "redbull", "cluster-roles", [PROD], jane_user, dry_run=True
    )
    (install,) = result.installs
    assert install.status == "planned" and install.result is None
    assert any("manual-sync" in note for note in install.notes)
    project = await gitlab.get_project("sigs/redbull")
    assert await gitlab.list_merge_requests(project.id) == []


async def test_each_mce_is_refused_on_its_own_and_the_others_open(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    # bmhgen is in both MCEs' own folders already: installed, refused; nothing else is affected.
    result = await services.changes.install_on_mces(
        "redbull", "bmhgen", [PREP, PROD], jane_user, dry_run=True
    )
    assert [i.status for i in result.installs] == ["refused", "refused"]
    assert result.installs[0].refused is not None
    assert result.installs[0].refused.details["rule"] == "installed"


async def test_an_mce_default_of_the_chart_is_refused_by_the_xor_rule(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    project = await gitlab.get_project("sigs/redbull")
    await gitlab.commit(
        project.id,
        branch="main",
        message="by hand",
        changes=[FileChange.create(RepoPath("defaults/mces/cluster-roles/values.yaml"), "{}\n")],
    )
    result = await services.changes.install_on_mces(
        "redbull", "cluster-roles", [PROD], jane_user, dry_run=True
    )
    (install,) = result.installs
    assert install.status == "refused" and install.refused is not None
    assert install.refused.details["rule"] == "xor"
    assert "a fleet default" in install.refused.detail


async def test_a_failed_mce_fails_alone_and_nothing_is_retried(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    commit = gitlab.commit

    async def refuse_prep(project_id: int, **kwargs: Any) -> Any:
        calls.append(str(kwargs.get("branch")))
        if "ocp4-prep-mce-site1-a" in str(kwargs.get("branch")):
            raise InvalidRequestError("GitLab refused the branch")
        return await commit(project_id, **kwargs)

    monkeypatch.setattr(gitlab, "commit", refuse_prep)
    result = await services.changes.install_on_mces(
        "redbull", "cluster-roles", [PREP, PROD], jane_user
    )
    assert [i.status for i in result.installs] == ["failed", "opened"]
    assert isinstance(result.installs[0].failed, InvalidRequestError)
    assert len(calls) == 2


async def test_once_gitlab_does_not_answer_no_more_are_started(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unreachable(project_id: int, **kwargs: Any) -> Any:
        raise GitUnavailableError("GitLab unreachable")

    monkeypatch.setattr(gitlab, "commit", unreachable)
    result = await services.changes.install_on_mces(
        "redbull", "cluster-roles", [PREP, PROD], jane_user
    )
    assert [i.status for i in result.installs] == ["failed", "failed"]
    assert all(isinstance(i.failed, GitUnavailableError) for i in result.installs)


async def test_whole_request_refusals(services: Day2Services, jane_user: User) -> None:
    hosted = "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1"
    with pytest.raises(ChangeRefusedError) as raised:
        await services.changes.install_on_mces("redbull", "cluster-roles", [hosted], jane_user)
    assert raised.value.details["rule"] == "not-an-mce"
    with pytest.raises(ChangeRefusedError) as raised:
        await services.changes.install_on_mces("redbull", "cluster-roles", [], jane_user)
    assert raised.value.details["rule"] == "no-mce"
    with pytest.raises(UnknownChartError):
        await services.changes.install_on_mces("redbull", "ghost", [PROD], jane_user)
    with pytest.raises(TeamReadOnlyError):
        await services.changes.install_on_mces("orca", "metrics", [PROD], jane_user)
