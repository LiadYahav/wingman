"""A syncPolicy ArgoCD's Application refuses is a lint error on the file that sets it."""

from __future__ import annotations

from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day2.application.services import Day2Services
from wingman_day2.domain.findings import Rule, Severity

BACKUP = "operators/backup/backup.yaml"


async def _write(gitlab: InMemoryGitLab, content: str) -> None:
    pid = (await gitlab.get_project("sigs/lynx")).id
    await gitlab.commit(
        pid,
        branch="main",
        message="test setup",
        changes=[FileChange.update(RepoPath(BACKUP), content, last_commit_id=None)],
    )


async def test_automated_true_is_an_error_on_the_layer_that_sets_it(
    services: Day2Services, gitlab: InMemoryGitLab
) -> None:
    await _write(
        gitlab,
        "repourl: http://gitlab.fake/helm-charts/sim-day2-helm-charts.git\n"
        "syncPolicy:\n  automated: true\n",
    )
    found = [f for f in await services.lints.report("lynx") if f.rule is Rule.SYNC_POLICY_INVALID]
    assert found
    assert {(f.severity, f.path, f.chart) for f in found} == {(Severity.ERROR, BACKUP, "backup")}
    assert "`syncPolicy.automated: true` is not a map" in found[0].message


async def test_enabled_false_is_manual_sync_and_no_error(
    services: Day2Services, gitlab: InMemoryGitLab
) -> None:
    await _write(
        gitlab,
        "repourl: http://gitlab.fake/helm-charts/sim-day2-helm-charts.git\n"
        "syncPolicy:\n  automated:\n    enabled: false\n    selfHeal: true\n",
    )
    report = await services.lints.report("lynx")
    assert Rule.SYNC_POLICY_INVALID not in {f.rule for f in report}
    entry = next(e for e in await services.catalog.entries("lynx") if e.chart == "backup")
    assert entry.sync_policy == {"automated": {"enabled": False, "selfHeal": True}}
