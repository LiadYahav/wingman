"""The upstream maps stay true, and scripts/upstream_diff.py reads them right.

Wingman mirrors two of the team's systems, server-scan and segments-manager.
``docs/integrations/<system>.yaml`` says which upstream files each Wingman
file follows and which upstream version Wingman matches; the script compares
the upstream between that version and a newer one. These tests keep the maps
in step with the code (every path exists; a file names its map exactly when
the map lists it; no file pins its own upstream commit) and hold the script to
a small local repository standing in for the upstream, so they need no network.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SYSTEMS = ("server-scan", "segments-manager")
SCANNED = ("apps", "dev")
"""Where a file may follow an upstream: the services, the web, the fixtures."""


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "wingman_upstream_diff", ROOT / "scripts" / "upstream_diff.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["wingman_upstream_diff"] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


upstream_diff = _load()


def _map(system: str) -> Any:
    """The system's map (the script's own type, loaded at run time)."""
    return upstream_diff.load_map(ROOT / "docs" / "integrations" / f"{system}.yaml")


def _texts() -> Iterator[tuple[str, str]]:
    """Every file git tracks (or would) under ``SCANNED``, with its text; binaries skipped."""
    listed = subprocess.run(  # noqa: S603 - a fixed argv, no shell
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *SCANNED],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode()
    for name in sorted(set(listed.split("\0")) - {""}):
        path = ROOT / name
        if not path.is_file():  # deleted in the working tree, not yet in the index
            continue
        try:
            yield name, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


# ── (a) and (b): the maps against the code ───────────────────────────────────


@pytest.mark.parametrize("system", SYSTEMS)
class TestTheMap:
    def test_every_wingman_path_exists_once(self, system: str) -> None:
        paths = [entry.wingman for entry in _map(system).files]
        assert [p for p in paths if not (ROOT / p).is_file()] == []
        assert sorted(p for p in set(paths) if paths.count(p) > 1) == []

    def test_upstream_paths_are_relative_to_the_upstream_repo(self, system: str) -> None:
        umap = _map(system)
        named = [*umap.watch, *umap.not_followed, *(p for e in umap.files for p in e.upstream)]
        assert [p for p in named if p.startswith(("/", "./")) or ".." in p] == []

    def test_a_file_names_this_map_exactly_when_the_map_lists_it(self, system: str) -> None:
        """A file that says it follows the upstream is listed, and a listed file says so.

        "Says so" is naming ``team-redbull/<repo>`` or this map's path; a listed
        file must name the map, so whoever edits it finds what it follows.
        """
        repo = _map(system).upstream
        pointer = f"docs/integrations/{system}.yaml"
        upstream = re.compile(rf"{re.escape(repo)}(?![\w-])")
        listed = {entry.wingman for entry in _map(system).files}
        names_it = {name for name, text in _texts() if pointer in text or upstream.search(text)}
        assert sorted(names_it - listed) == [], f"name {repo} but are not in {pointer}"
        assert sorted(p for p in listed if pointer not in (ROOT / p).read_text()) == [], (
            f"are in {pointer} but do not name it"
        )

    def test_no_file_pins_its_own_upstream_commit(self, system: str) -> None:
        """The version Wingman matches is the map's ``synced_at``, not a commit per file."""
        pinned = re.compile(rf"{re.escape(_map(system).upstream)} at [0-9a-f]{{7,40}}\b")
        assert [name for name, text in _texts() if pinned.search(text)] == []


# ── (c): the script, against a stand-in upstream ─────────────────────────────

MAP = """\
upstream: example/upstream
synced_at: v1.0.0
watch: [api/, ui/]
not_followed:
  - upstream: [api/skip.py]
    why: the stand-in's decision
files:
  - wingman: w/changed.py
    upstream: [api/a.py]
  - wingman: w/removed.ts
    upstream: [ui/c.ts]
  - wingman: w/same.py
    upstream: [api/b.py]
  - wingman: w/moved.ts
    upstream: [ui/d.ts]
    note: renamed upstream
"""


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)  # noqa: S603, S607


def _write(repo: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)


@pytest.fixture(scope="module")
def upstream(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Two tagged commits: a mapped change, a new and a skipped file, a removal, a rename."""
    repo = tmp_path_factory.mktemp("upstream")
    _git(repo, "init", "--quiet", "--initial-branch=main")
    moved = "export const d = 'a file long enough to be found again after its rename';\n"
    _write(
        repo,
        {"api/a.py": "a = 1\n", "api/b.py": "b = 1\n", "ui/c.ts": "c\n", "ui/d.ts": moved},
    )
    _write(repo, {"docs/x.md": "x\n"})
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "one")
    _git(repo, "tag", "v1.0.0")
    _write(repo, {"api/a.py": "a = 2\n", "api/new.py": "n\n", "api/skip.py": "s\n"})
    _write(repo, {"docs/x.md": "y\n"})
    _git(repo, "rm", "--quiet", "ui/c.ts")
    _git(repo, "mv", "ui/d.ts", "ui/e.ts")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "two")
    _git(repo, "tag", "v1.1.0")
    return repo


@pytest.fixture
def stand_in_map(tmp_path: Path) -> Path:
    path = tmp_path / "example.yaml"
    path.write_text(MAP)
    return path


def _changes(upstream: Path) -> list[Any]:
    return upstream_diff.changes_between(upstream, "v1.0.0", "v1.1.0")


class TestTheComparison:
    def test_each_entry_gets_the_changes_to_its_upstream_files(self, upstream: Path) -> None:
        umap = upstream_diff.parse_map(MAP)
        found = {
            e.wingman: [c.line() for c in upstream_diff.entry_changes(e, _changes(upstream))]
            for e in umap.files
        }
        assert found["w/changed.py"] == ["M    api/a.py"]
        assert found["w/removed.ts"] == ["D    ui/c.ts"]
        assert found["w/same.py"] == []
        assert [line.split()[1:] for line in found["w/moved.ts"]] == [["ui/d.ts", "->", "ui/e.ts"]]

    def test_a_watched_change_no_entry_follows_is_listed(self, upstream: Path) -> None:
        umap = upstream_diff.parse_map(MAP)
        found = upstream_diff.unmapped_watched(umap, _changes(upstream))
        # docs/ is not watched; api/skip.py is not followed on purpose.
        assert [c.path for c in found] == ["api/new.py"]

    def test_an_upstream_file_gone_at_the_target_is_listed(self, upstream: Path) -> None:
        umap = upstream_diff.parse_map(MAP)
        tree = upstream_diff.tree(upstream, "v1.1.0")
        assert upstream_diff.missing_upstream(umap, tree) == [
            ("w/removed.ts", "ui/c.ts"),
            ("w/moved.ts", "ui/d.ts"),
        ]

    def test_a_folder_covers_what_is_under_it(self) -> None:
        assert upstream_diff.covers("ui/", "ui/e.ts")
        assert not upstream_diff.covers("ui/", "uix/e.ts")
        assert not upstream_diff.covers("ui/c.ts", "ui/c.tsx")

    def test_the_target_is_the_newest_tag_or_the_maps_branch(self, upstream: Path) -> None:
        assert upstream_diff.default_target(upstream, upstream_diff.parse_map(MAP)) == "v1.1.0"
        on_main = upstream_diff.parse_map(MAP + "default_target: main\n")
        assert upstream_diff.default_target(upstream, on_main) == "main"


class TestTheReport:
    def test_it_prints_the_commits_and_the_three_lists(
        self, upstream: Path, stand_in_map: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            upstream_diff.main(["example", "--repo", str(upstream), "--map", str(stand_in_map)])
            == 0
        )
        out = capsys.readouterr().out
        assert out.startswith("example/upstream: synced_at v1.0.0 (")
        assert "-> v1.1.0 (" in out
        assert "1 upstream commit(s) since v1.0.0:" in out
        assert "1. Wingman files whose upstream changed (3 of 4):" in out
        assert "w/moved.ts  (renamed upstream)" in out
        assert "2. Upstream changes under watch that no map entry covers (1):" in out
        assert "3. Upstream files the map names that v1.1.0 does not have (2):" in out
        assert "ui/c.ts  (followed by w/removed.ts)" in out
        assert "+a = 2" not in out

    def test_patch_adds_the_upstream_diff_under_each_file(
        self, upstream: Path, stand_in_map: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = ["example", "v1.1.0", "--patch", "--repo", str(upstream), "--map", str(stand_in_map)]
        assert upstream_diff.main(args) == 0
        assert "      | +a = 2" in capsys.readouterr().out

    def test_nothing_new_says_wingman_matches(
        self, upstream: Path, stand_in_map: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = ["example", "v1.0.0", "--repo", str(upstream), "--map", str(stand_in_map)]
        assert upstream_diff.main(args) == 0
        assert "No upstream commit since v1.0.0: Wingman matches v1.0.0." in capsys.readouterr().out

    def test_from_compares_from_another_ref(
        self, upstream: Path, stand_in_map: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = [
            "example",
            "v1.0.0",
            "--from",
            "v1.1.0",
            "--repo",
            str(upstream),
            "--map",
            str(stand_in_map),
        ]
        assert upstream_diff.main(args) == 0
        assert "note: v1.0.0 does not contain v1.1.0" in capsys.readouterr().out

    def test_an_unknown_ref_or_map_is_a_usage_error(
        self, upstream: Path, stand_in_map: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            upstream_diff.main(
                ["example", "v9", "--repo", str(upstream), "--map", str(stand_in_map)]
            )
            == 2
        )
        assert "has no commit v9" in capsys.readouterr().err
        assert upstream_diff.main(["no-such-system", "--repo", str(upstream)]) == 2
        assert "the maps: segments-manager, server-scan" in capsys.readouterr().err


class TestTheMapsShape:
    @pytest.mark.parametrize(
        ("text", "error"),
        [
            ("upstream: a/b\nfiles: [{wingman: x, upstream: [y]}]\n", "no synced_at"),
            ("upstream: a/b\nsynced_at: v1\nfiles: []\n", "no files"),
            (
                "upstream: a/b\nsynced_at: v1\nfiles: [{wingman: x, upstream: []}]\n",
                "follows no upstream",
            ),
            ("upstream: a/b\nsynced_at: v1\nfiles: [{upstream: [y]}]\n", "needs a wingman path"),
            (
                "upstream: a/b\nsynced_at: v1\nnot_followed: [{upstream: [z]}]\n"
                "files: [{wingman: x, upstream: [y]}]\n",
                "needs a why",
            ),
        ],
    )
    def test_a_bad_map_says_what_is_wrong(self, text: str, error: str) -> None:
        with pytest.raises(upstream_diff.UpstreamError, match=error):
            upstream_diff.parse_map(text)
