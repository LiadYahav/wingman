#!/usr/bin/env python3
"""Fail unless a pytest JUnit report shows tests that ran and passed, with none skipped.

    python3 scripts/assert-junit.py REPORT.xml [--min-tests N]

pytest exits 0 when every selected test is skipped, so a suite gated on an
environment variable (the live GitLab contract, ADR-0005) can pass while
testing nothing. CI runs this after such a suite so it fails loudly instead.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET


def main(argv: list[str] | None = None) -> int:
    """Read the report and refuse an empty, skipped or failing run."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report")
    parser.add_argument("--min-tests", type=int, default=1)
    args = parser.parse_args(argv)
    root = ET.parse(args.report).getroot()  # noqa: S314 - a report this job just wrote
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = sum(int(suite.get("tests", "0")) for suite in suites)
    skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
    failed = sum(
        int(suite.get("failures", "0")) + int(suite.get("errors", "0")) for suite in suites
    )
    print(f"{args.report}: {total} tests, {skipped} skipped, {failed} failed or errored")
    if total < args.min_tests:
        print(f"::error::expected at least {args.min_tests} tests, {total} ran")
        return 1
    if skipped or failed:
        print("::error::every test must run and pass; a skipped test here means it tested nothing")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
