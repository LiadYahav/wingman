"""The decisions CI's own scripts make: release plan and notes, the npm audit and file sizes.

They run only in CI or the gate, where a wrong answer publishes the wrong
image or lets a vulnerability or an oversized file through, so the rules are
pinned here (ADR-0030, ADR-0031, ADR-0032, ADR-0056).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, file: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


release = _load("wingman_ci_release", "release.py")
npm_audit = _load("wingman_ci_npm_audit", "npm-audit.py")
assert_junit = _load("wingman_ci_assert_junit", "assert-junit.py")
file_size = _load("wingman_ci_file_size", "check-file-size.py")

HEAD = "a" * 40
OTHER = "b" * 40


class TestReleasePlan:
    """The guard on the version semantic-version computes (ADR-0031)."""

    def test_a_new_version_above_every_release_is_released(self) -> None:
        plan = release.decide(
            "3.0.1", {"v3.0.0": OTHER}, HEAD, {"v3.0.0", "latest", "abc1234", "sha-abc1234"}
        )
        assert plan.tag == "v3.0.1"
        assert plan.version == "3.0.1"
        assert "previous: v3.0.0" in plan.reason

    def test_the_first_release_has_nothing_to_compare_with(self) -> None:
        assert release.decide("1.0.0", {}, HEAD, set()).tag == "v1.0.0"

    def test_a_version_tagged_on_another_commit_is_refused(self) -> None:
        with pytest.raises(release.PlanError, match="refusing to re-tag"):
            release.decide("3.0.1", {"v3.0.1": OTHER}, HEAD, set())

    def test_a_rerun_on_the_tagged_commit_is_allowed(self) -> None:
        plan = release.decide("3.0.1", {"v3.0.1": HEAD}, HEAD, {"3.0.1", "3.0", "3"})
        assert "re-run" in plan.reason

    def test_a_rerun_behind_a_newer_release_fails(self) -> None:
        with pytest.raises(release.PlanError, match="below the newest release"):
            release.decide("3.0.1", {"v3.0.1": HEAD, "v3.0.2": OTHER}, HEAD, set())

    @pytest.mark.parametrize("published", ["v3.0.1", "3.0.1"])
    def test_an_image_without_a_git_tag_is_never_overwritten(self, published: str) -> None:
        with pytest.raises(release.PlanError, match="never re-pointed"):
            release.decide("3.0.1", {"v3.0.0": OTHER}, HEAD, {published, "latest"})

    @pytest.mark.parametrize(
        ("git_tags", "registry"),
        [
            ({"v3.0.0": OTHER}, set()),
            ({}, {"v3.0.0"}),
            ({}, {"3.0.0"}),
            ({"v2.10.0": OTHER}, set()),
        ],
    )
    def test_a_version_below_the_newest_release_fails(
        self, git_tags: dict[str, str], registry: set[str]
    ) -> None:
        with pytest.raises(release.PlanError, match="below the newest release"):
            release.decide("2.9.0", git_tags, HEAD, registry)

    def test_versions_compare_as_numbers_not_strings(self) -> None:
        assert release.decide("1.10.0", {"v1.9.0": OTHER}, HEAD, {"1.9.0"}).tag == "v1.10.0"

    @pytest.mark.parametrize("version", ["3.0", "v3.0.0", "3.0.0-rc1", "03.0.0", ""])
    def test_a_malformed_version_fails(self, version: str) -> None:
        with pytest.raises(release.PlanError, match=r"X\.Y\.Z"):
            release.decide(version, {}, HEAD, set())

    def test_rolling_and_non_version_tags_are_ignored(self) -> None:
        plan = release.decide(
            "1.0.0", {"vnext": OTHER, "v9": OTHER}, HEAD, {"latest", "v99.0", "99", "sha-1234567"}
        )
        assert plan.tag == "v1.0.0"

    def test_the_version_comes_from_the_command_line_not_a_file(self) -> None:
        assert not (ROOT / "VERSION").exists()
        with pytest.raises(SystemExit):
            release.main(["plan"])  # --version is required


class TestPublishedTags:
    """The tags operators deploy by: server-scan's set (ADR-0031, docs/ops/images.md)."""

    def test_publish_pushes_the_release_set(self) -> None:
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        steps = workflow["jobs"]["publish"]["steps"]
        meta = next(s for s in steps if s.get("id") == "meta")
        value = "value=${{ needs.release-plan.outputs.tag }}"
        assert meta["with"]["tags"].splitlines() == [
            f"type=semver,pattern={{{{version}}}},{value}",
            f"type=semver,pattern={{{{major}}}}.{{{{minor}}}},{value}",
            f"type=semver,pattern={{{{major}}}},{value}",
            "type=raw,value=latest",
            "type=sha,prefix=sha-",
        ]


class TestReleaseNotes:
    def test_subjects_are_grouped_and_internal_types_dropped(self) -> None:
        notes = release.render_notes(
            "v3.0.0",
            "v2.0.0",
            [
                "feat(day1): read site values",
                "fix: keep the MR branch",
                "feat!: drop the legacy API",
                "ci: pin zizmor",
                "refactor: split the router",
                "Merge-free subject without a type",
            ],
            ["ghcr.io/team/wingman-web"],
        )
        assert (
            notes.index("### Breaking") < notes.index("### New features") < notes.index("### Fixed")
        )
        assert "- drop the legacy API" in notes
        assert "- read site values" in notes
        assert "pin zizmor" not in notes
        assert "split the router" not in notes
        assert "### Other\n\n- Merge-free subject without a type" in notes
        assert "- `ghcr.io/team/wingman-web:3.0.0`" in notes
        assert notes.endswith("**Full changelog:** v2.0.0...v3.0.0\n")

    def test_a_release_with_nothing_operator_visible_says_so(self) -> None:
        notes = release.render_notes("v1.0.1", "", ["ci: bump", "test: more"], [])
        assert notes == "No operator-visible changes in this release.\n"


def _report(*advisories: tuple[str, str, str]) -> dict[str, Any]:
    vulnerabilities: dict[str, Any] = {}
    for ghsa, package, severity in advisories:
        entry = vulnerabilities.setdefault(package, {"via": [], "fixAvailable": True})
        entry["via"].append(
            {
                "name": package,
                "severity": severity,
                "title": f"{package} advisory",
                "url": f"https://github.com/advisories/{ghsa}",
            }
        )
    vulnerabilities["parent"] = {"via": ["next"], "fixAvailable": False}  # names only
    return {"vulnerabilities": vulnerabilities}


class TestNpmAudit:
    def test_advisories_are_keyed_by_ghsa_and_name_only_entries_skipped(self) -> None:
        found = npm_audit.advisories(
            _report(
                ("GHSA-aaaa-bbbb-cccc", "next", "critical"), ("GHSA-dddd-eeee-ffff", "zod", "high")
            )
        )
        assert set(found) == {"GHSA-aaaa-bbbb-cccc", "GHSA-dddd-eeee-ffff"}
        assert found["GHSA-aaaa-bbbb-cccc"]["package"] == "next"

    def test_an_advisory_missing_from_the_allowlist_fails(self) -> None:
        found = npm_audit.advisories(_report(("GHSA-aaaa-bbbb-cccc", "next", "critical")))
        errors = npm_audit.compare(found, set())
        assert errors == [
            "not allowlisted: GHSA-aaaa-bbbb-cccc next (critical): next advisory "
            "https://github.com/advisories/GHSA-aaaa-bbbb-cccc"
        ]

    def test_an_entry_npm_no_longer_reports_fails_so_the_list_only_shrinks(self) -> None:
        errors = npm_audit.compare({}, {"GHSA-aaaa-bbbb-cccc"})
        assert errors == ["no longer reported, remove it from the allowlist: GHSA-aaaa-bbbb-cccc"]

    def test_the_allowlist_reads_the_first_word_and_skips_comments(self) -> None:
        text = "# header\n\nGHSA-aaaa-bbbb-cccc  next  critical  # why\n  # indented comment\n"
        assert npm_audit.allowed(text) == {"GHSA-aaaa-bbbb-cccc"}

    def test_a_line_that_is_not_a_ghsa_id_is_refused(self) -> None:
        with pytest.raises(SystemExit, match="not a GHSA id"):
            npm_audit.allowed("next  critical\n")

    def test_the_committed_allowlist_parses(self) -> None:
        text = (ROOT / "scripts/npm-audit-allowlist.txt").read_text(encoding="utf-8")
        assert npm_audit.allowed(text)


class TestFileSize:
    """The size ratchet (ADR-0056): limits per kind, and a baseline that only shrinks."""

    PAGE = "apps/web/app/(app)/clusters/new/page.tsx"

    @pytest.mark.parametrize(
        ("path", "limit"),
        [
            ("apps/day2-service/src/wingman_day2/api/v1/schemas.py", 500),
            ("apps/web/app/(app)/clusters/[name]/page.tsx", 500),
            ("apps/web/lib/day2.ts", 500),
            ("scripts/release.py", 500),
            ("packages/wingman-core/src/wingman_core/testing/gitlab_contract.py", 500),
            ("apps/day1-service/tests/api/test_placement_api.py", 800),
            ("tests/repo/test_web_docs_contract.py", 800),
            ("apps/web/e2e/tests/mce-placement.spec.ts", 800),
            ("apps/web/e2e/fixtures/api-handlers.ts", 800),
        ],
    )
    def test_source_and_tests_have_their_own_limits(self, path: str, limit: int) -> None:
        assert file_size.limit_for(path) == limit

    @pytest.mark.parametrize(
        "path",
        [
            "apps/web/components/ui/select.tsx",  # shadcn's generated components
            "apps/day2-service/tests/oracle/render_chain.py",  # vendored
            "apps/web/next-env.d.ts",
            "dev/gitlab-fixtures/wingman/cluster-specs/x.py",
            "apps/web/eslint.config.mjs",
            "docs/adr/README.md",
        ],
    )
    def test_generated_vendored_and_other_files_are_not_checked(self, path: str) -> None:
        assert file_size.limit_for(path) is None

    @pytest.mark.parametrize(("data", "lines"), [(b"", 0), (b"a\n", 1), (b"a\nb", 2), (b"\n\n", 2)])
    def test_lines_are_counted_as_wc_l_does_plus_an_unterminated_last(
        self, data: bytes, lines: int
    ) -> None:
        assert file_size.count_lines(data) == lines

    def test_a_new_file_over_the_limit_fails_and_the_baseline_takes_no_new_files(self) -> None:
        errors, _ = file_size.compare({"apps/web/lib/new.ts": 501}, {})
        assert errors == [
            "apps/web/lib/new.ts: 501 lines, over the 500-line limit: split it (ADR-0056); "
            "the baseline takes no new files"
        ]

    def test_files_within_their_limit_pass(self) -> None:
        sizes = {"apps/web/lib/a.ts": 500, "apps/day1-service/tests/test_a.py": 800}
        assert file_size.compare(sizes, {}) == ([], [])

    def test_a_listed_file_may_not_grow_past_its_ceiling(self) -> None:
        errors, _ = file_size.compare({self.PAGE: 1895}, {self.PAGE: 1894})
        assert errors == [
            f"{self.PAGE}: 1895 lines, past its ceiling of 1894: move code out before adding "
            "to it (ADR-0056); a ceiling is never raised"
        ]

    def test_a_listed_file_may_shrink_and_is_told_to_lower_its_ceiling(self) -> None:
        assert file_size.compare({self.PAGE: 1894}, {self.PAGE: 1894}) == ([], [])
        errors, notes = file_size.compare({self.PAGE: 1200}, {self.PAGE: 1894})
        assert errors == []
        assert notes == [f"{self.PAGE}: 1200 lines, below its ceiling of 1894: lower it"]

    def test_a_listed_file_back_within_the_limit_must_leave_the_baseline(self) -> None:
        errors, _ = file_size.compare({self.PAGE: 500}, {self.PAGE: 1894})
        assert errors == [
            f"{self.PAGE}: 500 lines, within the 500-line limit now: "
            "remove it from file-size-baseline.txt"
        ]

    def test_an_entry_for_a_file_that_is_gone_or_unchecked_fails(self) -> None:
        errors, _ = file_size.compare(
            {}, {self.PAGE: 1894, "apps/web/components/ui/select.tsx": 900}
        )
        assert errors == [
            f"{self.PAGE}: listed in file-size-baseline.txt but no longer exists: remove its line",
            "apps/web/components/ui/select.tsx: listed in file-size-baseline.txt but is not "
            "a checked file: remove its line",
        ]

    def test_the_baseline_reads_ceiling_then_path_and_skips_comments(self) -> None:
        text = f"# header\n\n 1894  {self.PAGE}  # why\n  # indented\n"
        assert file_size.parse_baseline(text) == {self.PAGE: 1894}

    @pytest.mark.parametrize("line", [f"{PAGE}  1894", "1894", "many  apps/web/lib/a.ts"])
    def test_a_malformed_baseline_line_is_refused(self, line: str) -> None:
        with pytest.raises(SystemExit, match="not '<ceiling>  <path>'"):
            file_size.parse_baseline(line)

    def test_a_path_listed_twice_is_refused(self) -> None:
        with pytest.raises(SystemExit, match="listed twice"):
            file_size.parse_baseline(f"1894  {self.PAGE}\n1000  {self.PAGE}\n")

    def test_every_committed_entry_is_over_its_limit(self) -> None:
        text = (ROOT / "scripts/file-size-baseline.txt").read_text(encoding="utf-8")
        ceilings = file_size.parse_baseline(text)
        assert ceilings
        for path, ceiling in ceilings.items():
            limit = file_size.limit_for(path)
            assert limit is not None, path
            assert ceiling > limit, path


class TestAssertJunit:
    @staticmethod
    def _write(tmp_path: Path, tests: int, skipped: int, failures: int = 0) -> str:
        path = tmp_path / "report.xml"
        path.write_text(
            f'<testsuites><testsuite name="pytest" tests="{tests}" skipped="{skipped}" '
            f'failures="{failures}" errors="0"/></testsuites>',
            encoding="utf-8",
        )
        return str(path)

    def test_a_run_that_passed_everything_passes(self, tmp_path: Path) -> None:
        assert assert_junit.main([self._write(tmp_path, 27, 0), "--min-tests", "27"]) == 0

    @pytest.mark.parametrize(
        ("tests", "skipped", "failures"),
        [(27, 27, 0), (27, 1, 0), (27, 0, 1), (0, 0, 0), (26, 0, 0)],
    )
    def test_a_skipped_failed_or_short_run_fails(
        self, tmp_path: Path, tests: int, skipped: int, failures: int
    ) -> None:
        report = self._write(tmp_path, tests, skipped, failures)
        assert assert_junit.main([report, "--min-tests", "27"]) == 1
