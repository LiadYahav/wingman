"""The words day2's messages use (ADR-0043's amendment): Sig values, never "team default".

Since 3.13.2 the UI calls an add-on's team-level layer (``operators/<chart>/``)
Sig values; since 3.20.1 day2's errors, lint findings and warnings say so too.
The API keeps its names (``update-team-default``, ``update_team_default``), and
so do docstrings and the schemas' ``description``s that document it: only the
strings a person reads are checked here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "src" / "wingman_day2"
OLD = "team default"


def _messages(source: str) -> list[str]:
    """The string literals in ``source`` but its docstrings and ``description=`` arguments."""
    tree = ast.parse(source)
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                skip.add(id(first.value))
        elif isinstance(node, ast.keyword) and node.arg == "description":
            skip.update(id(n) for n in ast.walk(node.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
    ]


def test_the_guard_reads_messages_and_skips_what_documents_the_api() -> None:
    source = '''
"""The team default."""
def f(chart):
    """Edit the team default."""
    note = Field(default=None, description="null: the team default's.")
    raise Refused(
        f"{chart} would get it (the "
        f"team default or its pin)"
    )
'''
    found = [s for s in _messages(source) if OLD in s]
    assert found == [" would get it (the team default or its pin)"]
    assert (SOURCE / "main.py").is_file() and len(list(SOURCE.rglob("*.py"))) > 20


@pytest.mark.parametrize("path", sorted(SOURCE.rglob("*.py")), ids=lambda p: p.name)
def test_no_message_says_team_default(path: Path) -> None:
    said = [s for s in _messages(path.read_text(encoding="utf-8")) if OLD in s.lower()]
    assert said == [], f"{path.relative_to(SOURCE)}: say Sig values, not {OLD!r}: {said}"
