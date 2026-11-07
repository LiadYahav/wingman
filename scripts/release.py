#!/usr/bin/env python3
"""Release helpers for CI (ADR-0030): the version plan, registry tags and release notes.

    python3 scripts/release.py plan [--registry-tags FILE]
    python3 scripts/release.py registry-tags IMAGE [IMAGE ...]
    python3 scripts/release.py notes TAG [--image IMAGE ...]

A release is cut by bumping the root VERSION file. ``plan`` decides whether
this commit cuts one and refuses a VERSION below the newest release, so a
version tag never moves and never goes backwards. ``notes`` writes the release
notes from the Conventional Commit subjects since the previous tag (there is
no CHANGELOG, as in server-scan and herzi). Standard library only: it runs on
a bare runner.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
SUBJECT = re.compile(r"^(?P<type>[a-z]+)(?P<scope>\([^)]*\))?(?P<bang>!)?: (?P<rest>.+)$")
NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')
# Operator-visible changes only; refactor/test/chore/ci/build/style are dropped.
HEADINGS = {
    "breaking": "Breaking",
    "feat": "New features",
    "fix": "Fixed",
    "perf": "Performance",
    "docs": "Documentation",
}

Version = tuple[int, int, int]


class PlanError(Exception):
    """VERSION cannot be released: it is malformed or below the newest release."""


@dataclass(frozen=True)
class Plan:
    """Whether this commit publishes ``tag`` as a release, and why."""

    version: str
    tag: str
    release: bool
    reason: str


def parse_tag(tag: str) -> Version | None:
    """``v1.2.3`` as a comparable tuple; ``None`` for anything else."""
    match = SEMVER.match(tag[1:]) if tag.startswith("v") else None
    if match is None:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return (major, minor, patch)


def decide(version: str, git_tags: dict[str, str], head: str, registry_tags: set[str]) -> Plan:
    """The release plan for ``version`` at commit ``head``.

    ``git_tags`` maps each tag to the commit it points at; ``registry_tags`` are
    the image tags already published. A version that already exists is never
    re-pointed: unless its git tag is on this very commit (a re-run), the
    commit publishes its ``<sha>`` and ``latest`` tags only.
    """
    if not SEMVER.match(version):
        raise PlanError(f"VERSION must be X.Y.Z (digits only), got {version!r}")
    tag = f"v{version}"
    released = [t for t in {*git_tags, *registry_tags} if parse_tag(t) is not None]
    newest = max(released, key=lambda t: parse_tag(t) or (0, 0, 0), default=None)
    if newest is not None and (parse_tag(newest) or (0, 0, 0)) > (parse_tag(tag) or (0, 0, 0)):
        raise PlanError(
            f"VERSION {version} is below the newest release {newest}; versions only move forward"
        )
    if tag in git_tags:
        if git_tags[tag] == head:
            return Plan(version, tag, True, f"{tag} already points at this commit: a re-run")
        return Plan(
            version,
            tag,
            False,
            f"{tag} was released at {git_tags[tag][:7]}; this commit publishes <sha> and latest "
            "only. Bump VERSION to cut a release",
        )
    if tag in registry_tags:
        return Plan(
            version,
            tag,
            False,
            f"{tag} is already in the registry without a git tag (published before releases "
            "were tagged) and is never re-pointed. Bump VERSION to cut a release",
        )
    return Plan(version, tag, True, f"new release {tag} (previous: {newest or 'none'})")


def render_notes(tag: str, previous: str, subjects: list[str], images: list[str]) -> str:
    """Release notes grouped by Conventional Commit type, as server-scan and herzi write them."""
    groups: dict[str, list[str]] = {}
    other: list[str] = []
    for line in (s.strip() for s in subjects):
        if not line:
            continue
        match = SUBJECT.match(line)
        if match is None:
            other.append(line)
            continue
        key = "breaking" if match["bang"] else match["type"]
        if key in HEADINGS:
            groups.setdefault(key, []).append(match["rest"])
    out: list[str] = []
    for key, heading in HEADINGS.items():
        if groups.get(key):
            out += [f"### {heading}", "", *(f"- {item}" for item in groups[key]), ""]
    if other:
        out += ["### Other", "", *(f"- {item}" for item in other), ""]
    if not out:
        out = ["No operator-visible changes in this release.", ""]
    if images:
        out += ["### Images", "", *(f"- `{image}:{tag}`" for image in images), ""]
    if previous:
        out.append(f"**Full changelog:** {previous}...{tag}")
    return "\n".join(out).rstrip("\n") + "\n"


def _git(*args: str, check: bool = True) -> str:
    # git from PATH with arguments this module builds; nothing comes from a user.
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_tags() -> dict[str, str]:
    """Every ``v*`` tag and the commit it points at (annotated tags peeled)."""
    lines = _git(
        "for-each-ref", "refs/tags/v*", "--format=%(refname:short) %(*objectname) %(objectname)"
    ).splitlines()
    tags: dict[str, str] = {}
    for line in lines:
        name, *shas = line.split()
        tags[name] = shas[0]
    return tags


def _registry_tags(image: str, token: str, actor: str) -> set[str]:
    """Every tag of ``image`` (``host/owner/name``) through the registry's v2 API.

    GHCR answers 403 both for a repository that does not exist yet and for one
    this token cannot read. Both count as "no tags": a token that cannot read a
    package cannot push to it either, so the publish step fails loudly instead.
    """
    host, _, repo = image.partition("/")
    query = urllib.parse.urlencode({"scope": f"repository:{repo}:pull", "service": host})
    request = urllib.request.Request(f"https://{host}/token?{query}")
    if token:
        basic = b64encode(f"{actor or 'token'}:{token}".encode()).decode()
        request.add_header("Authorization", f"Basic {basic}")
    tags: set[str] = set()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            bearer = json.load(response)["token"]
        url: str | None = f"https://{host}/v2/{repo}/tags/list?n=1000"
        while url:
            page = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}"})  # noqa: S310
            with urllib.request.urlopen(page, timeout=30) as response:  # noqa: S310
                tags.update(json.load(response).get("tags") or [])
                link = NEXT_LINK.search(response.headers.get("Link", ""))
            url = urllib.parse.urljoin(f"https://{host}", link.group(1)) if link else None
    except urllib.error.HTTPError as exc:
        if exc.code not in (401, 403, 404) or tags:
            raise
        print(f"{image}: no readable tags (HTTP {exc.code}), counted as none", file=sys.stderr)
        return set()
    return tags


def _write_outputs(values: dict[str, str]) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with Path(path).open("a", encoding="utf-8") as out:
            out.writelines(f"{key}={value}\n" for key, value in values.items())


def main(argv: list[str] | None = None) -> int:
    """Run one subcommand."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    plan_cmd = commands.add_parser("plan", help="decide whether this commit cuts a release")
    plan_cmd.add_argument("--registry-tags", type=Path, help="file of published image tags")
    tags_cmd = commands.add_parser("registry-tags", help="print every tag of the given images")
    tags_cmd.add_argument("images", nargs="+")
    notes_cmd = commands.add_parser("notes", help="release notes for TAG at HEAD")
    notes_cmd.add_argument("tag")
    notes_cmd.add_argument("--image", action="append", default=[])
    args = parser.parse_args(argv)

    if args.command == "registry-tags":
        token = os.environ.get("GHCR_TOKEN", "")
        actor = os.environ.get("GITHUB_ACTOR", "")
        found: set[str] = set()
        for image in args.images:
            found |= _registry_tags(image, token, actor)
        if found:
            print("\n".join(sorted(found)))
        return 0

    if args.command == "notes":
        previous = _git(
            "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", "HEAD^", check=False
        )
        span = f"{previous}..HEAD" if previous else "HEAD"
        subjects = _git("log", "--no-merges", "--format=%s", span).splitlines()
        sys.stdout.write(render_notes(args.tag, previous, subjects, args.image))
        return 0

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    registry: set[str] = set()
    if args.registry_tags:
        registry = set(args.registry_tags.read_text(encoding="utf-8").split())
    try:
        plan = decide(version, _git_tags(), _git("rev-parse", "HEAD"), registry)
    except PlanError as exc:
        print(f"::error::{exc}")
        return 1
    print(f"VERSION {plan.version}: {'release' if plan.release else 'no release'}. {plan.reason}")
    _write_outputs({"version": plan.version, "tag": plan.tag, "release": str(plan.release).lower()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
