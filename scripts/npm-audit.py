#!/usr/bin/env python3
"""npm audit, blocking, against an allowlist that may only shrink.

    python3 scripts/npm-audit.py           # fail on an advisory not allowlisted, or a stale entry
    python3 scripts/npm-audit.py --list    # print today's advisories as allowlist lines

Every advisory ``npm audit`` reports for the root package-lock.json (every
workspace, dev dependencies included, every severity: what server-scan's
plain ``npm audit`` gates) must be listed by its GHSA id in
scripts/npm-audit-allowlist.txt, with why it is accepted and what fixes it.
An entry npm no longer reports fails too, so a fix removes its entries in the
same change and the list can only shrink (server-scan's baseline rule).
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / "scripts" / "npm-audit-allowlist.txt"
GHSA = re.compile(r"^GHSA(-[0-9a-z]{4}){3}$")


def advisories(report: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Every advisory in an ``npm audit --json`` report, by GHSA id."""
    found: dict[str, dict[str, str]] = {}
    for vulnerability in report.get("vulnerabilities", {}).values():
        for via in vulnerability.get("via", []):
            if not isinstance(via, dict):
                continue  # a package name: the advisory is listed under that package
            ghsa = str(via["url"]).rstrip("/").rsplit("/", 1)[-1]
            found[ghsa] = {
                "package": str(via["name"]),
                "severity": str(via["severity"]),
                "title": str(via["title"]),
                "url": str(via["url"]),
            }
    return found


def fix_hint(report: dict[str, Any], package: str) -> str:
    """What ``npm audit`` says would fix ``package``, in a few words."""
    fix = report.get("vulnerabilities", {}).get(package, {}).get("fixAvailable")
    if fix is True:
        return "fix: an in-range update"
    if isinstance(fix, dict):
        major = " (semver major)" if fix.get("isSemVerMajor") else ""
        return f"fix: {fix.get('name')}@{fix.get('version')}{major}"
    return "no fix released"


def allowed(text: str) -> set[str]:
    """The GHSA ids in an allowlist: the first word of each non-comment line."""
    ids: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        words = line.split("#", 1)[0].split()
        if not words:
            continue
        if not GHSA.match(words[0]):
            raise SystemExit(f"{ALLOWLIST.name}:{number}: not a GHSA id: {words[0]!r}")
        ids.add(words[0])
    return ids


def compare(found: dict[str, dict[str, str]], allow: set[str]) -> list[str]:
    """One error line per advisory not allowlisted and per allowlisted one no longer reported."""
    errors = [
        f"not allowlisted: {ghsa} {info['package']} ({info['severity']}): "
        f"{info['title']} {info['url']}"
        for ghsa, info in sorted(found.items(), key=lambda item: (item[1]["package"], item[0]))
        if ghsa not in allow
    ]
    errors += [
        f"no longer reported, remove it from the allowlist: {ghsa}"
        for ghsa in sorted(allow - found.keys())
    ]
    return errors


def run_audit() -> dict[str, Any]:
    """``npm audit --json`` for the root lockfile; exits loudly if npm could not audit."""
    result = subprocess.run(
        ["npm", "audit", "--json"],  # noqa: S607 - npm from PATH, fixed arguments
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"npm audit produced no report:\n{result.stderr}") from None
    if "error" in report or "vulnerabilities" not in report:
        raise SystemExit(f"npm audit failed: {json.dumps(report.get('error', report))}")
    return report


def main(argv: list[str] | None = None) -> int:
    """Check the audit against the allowlist, or print it as allowlist lines."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--list", action="store_true", help="print the advisories as allowlist lines"
    )
    args = parser.parse_args(argv)
    report = run_audit()
    found = advisories(report)
    if args.list:
        for ghsa, info in sorted(found.items(), key=lambda item: (item[1]["package"], item[0])):
            hint = fix_hint(report, info["package"])
            print(f"{ghsa}  {info['package']:<26} {info['severity']:<9} {hint}  # {info['title']}")
        return 0
    errors = compare(found, allowed(ALLOWLIST.read_text(encoding="utf-8")))
    for error in errors:
        print(f"::error::npm audit: {error}")
    if errors:
        return 1
    counts = report.get("metadata", {}).get("vulnerabilities", {})
    print(f"npm audit: {len(found)} advisories, every one allowlisted ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
