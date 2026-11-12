"""The in-place editor for deploy configs: only what changes moves, comments stay (ADR-0043)."""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from wingman_day2.domain.errors import ChangeRefusedError
from wingman_day2.domain.yaml_text import dump_yaml, edit_mapping_text, same_value

# The shape of defaults/mces/dhcp-api-token/dhcp-api-token.yaml: comments everywhere.
TOKEN = """\
# The DHCP API bearer token, deployed once per MCE in-cluster.
projectNamespace: dhcp-scope-manager
# repourl, all lowercase.
repourl: https://gitlab.example/helm-charts/dhcp-scope-manager.git
targetRevision: main  # the default branch
path: charts/dhcp-api-token
syncPolicy:
  automated:
    selfHeal: true
    # prune: true so deleting this folder removes the Secret.
    prune: true
  syncOptions:
    # Nothing else creates this namespace on an MCE.
    - CreateNamespace=true
"""


def doc(text: str) -> dict[str, Any]:
    return yaml.safe_load(text) or {}


def edit(text: str, **changes: object) -> str:
    new = doc(text)
    for key, value in changes.items():
        if value is None:
            new.pop(key, None)
        else:
            new[key] = value
    return edit_mapping_text(text, new, path="x.yaml")


def changed_lines(old: str, new: str) -> tuple[list[str], list[str]]:
    a, b = old.splitlines(), new.splitlines()
    return [x for x in a if x not in b], [x for x in b if x not in a]


def test_a_nested_scalar_changes_on_its_line_and_every_comment_stays() -> None:
    policy = doc(TOKEN)["syncPolicy"]
    policy["automated"]["prune"] = False
    out = edit(TOKEN, syncPolicy=policy)
    assert changed_lines(TOKEN, out) == (["    prune: true"], ["    prune: false"])


def test_a_scalar_keeps_its_line_comment() -> None:
    out = edit(TOKEN, targetRevision="3.3.0")
    assert changed_lines(TOKEN, out) == (
        ["targetRevision: main  # the default branch"],
        ["targetRevision: 3.3.0  # the default branch"],
    )


def test_a_list_is_rewritten_below_the_comments_at_its_head() -> None:
    policy = doc(TOKEN)["syncPolicy"]
    policy["syncOptions"] = ["CreateNamespace=true", "ServerSideApply=true"]
    out = edit(TOKEN, syncPolicy=policy)
    assert changed_lines(TOKEN, out) == ([], ["    - ServerSideApply=true"])
    assert out.index("# Nothing else") < out.index("- CreateNamespace=true")


def test_a_removed_key_takes_its_own_lines_and_never_a_comment() -> None:
    out = edit(TOKEN, repourl=None)
    assert changed_lines(TOKEN, out) == (
        ["repourl: https://gitlab.example/helm-charts/dhcp-scope-manager.git"],
        [],
    )
    policy = doc(TOKEN)["syncPolicy"]
    del policy["automated"]
    out = edit(TOKEN, syncPolicy=policy)
    assert "selfHeal" not in out and "    prune: true" not in out
    # The comment inside the removed block stays, for a person to delete in the MR.
    assert "# prune: true so" in out and "# Nothing else creates" in out


def test_a_file_header_and_the_last_comment_of_the_block_before_stay() -> None:
    # Review of 3.8.0: resetting targetRevision, the first key, took the file's header with it,
    # and removing a key took the indented last comment of the block above it.
    text = (
        "# The kyverno team default: why it prunes is in ARCHITECTURE.md.\n"
        "targetRevision: 3.2.0\n"
        "syncPolicy:\n"
        "  automated:\n"
        "    prune: true\n"
        "  # selfHeal stays off: kyverno rewrites its own webhooks.\n"
        "projectNamespace: kyverno\n"
    )
    out = edit(text, targetRevision=None, projectNamespace=None)
    assert out == (
        "# The kyverno team default: why it prunes is in ARCHITECTURE.md.\n"
        "syncPolicy:\n"
        "  automated:\n"
        "    prune: true\n"
        "  # selfHeal stays off: kyverno rewrites its own webhooks.\n"
    )


def test_new_keys_go_after_the_last_key_of_their_mapping_in_the_team_style() -> None:
    text = "projectNamespace: kyverno\nsyncPolicy:\n  syncOptions:\n    - CreateNamespace=true\n"
    new = doc(text)
    new["syncPolicy"]["automated"] = {"prune": False, "selfHeal": True}
    new["ignoreDifferences"] = [{"kind": "Secret", "jsonPointers": ["/data"]}]
    out = edit_mapping_text(text, new, path="x")
    assert out == (
        "projectNamespace: kyverno\n"
        "syncPolicy:\n"
        "  syncOptions:\n"
        "    - CreateNamespace=true\n"
        "  automated:\n"
        "    prune: false\n"
        "    selfHeal: true\n"
        "ignoreDifferences:\n"
        "  - kind: Secret\n"
        "    jsonPointers:\n"
        "      - /data\n"
    )


def test_a_miscased_key_is_renamed_where_it_stands() -> None:
    text = "projectNamespace: kyverno\nrepoUrl: https://a/b.git\ntargetRevision: main\n"
    new = {"projectNamespace": "kyverno", "repourl": "https://a/c.git", "targetRevision": "main"}
    out = edit_mapping_text(text, new, path="x", renames={"repoUrl": "repourl"})
    assert out == "projectNamespace: kyverno\nrepourl: https://a/c.git\ntargetRevision: main\n"


def test_an_empty_file_gets_the_keys_and_keeps_its_comments() -> None:
    assert edit_mapping_text("", {"a": 1}, path="x") == "a: 1\n"
    assert edit_mapping_text("{}\n", {"a": [1]}, path="x") == "a:\n  - 1\n"
    assert edit_mapping_text("# why\n{}\n", {"a": 1}, path="x") == "# why\na: 1\n"
    # A removed key leaves every comment where it was.
    assert edit_mapping_text("# a's\na: 1\n", {}, path="x") == "# a's\n{}\n"
    assert edit_mapping_text("# file\n\na: 1\n", {}, path="x") == "# file\n\n{}\n"


def test_types_are_kept_exactly() -> None:
    out = edit_mapping_text("a: '3'\nb: true\n", {"a": 3, "b": "true"}, path="x")
    assert yaml.safe_load(out) == {"a": 3, "b": "true"}
    assert same_value(yaml.safe_load(out)["b"], "true")
    assert not same_value(True, 1) and not same_value("3", 3) and same_value({"a": [1]}, {"a": [1]})


@pytest.mark.parametrize(
    ("text", "new"),
    [
        ("a:\n  - x  # keep\n  - y\n", {"a": ["z"]}),
        ("a:\n  - x\n  # between\n  - y\n", {"a": ["z"]}),
        ("a: 1\n---\nb: 2\n", {"a": 2}),
        ("a:\n\t- x\n", {"a": ["z"]}),
        ("- a\n- b\n", {"a": 1}),
    ],
)
def test_layouts_it_cannot_edit_exactly_are_refused(text: str, new: dict[str, object]) -> None:
    with pytest.raises(ChangeRefusedError) as raised:
        edit_mapping_text(text, new, path="x.yaml")
    assert raised.value.details["rule"] == "deploy-config-layout"


def test_a_whole_file_dump_indents_lists() -> None:
    assert dump_yaml({"syncPolicy": {"syncOptions": ["CreateNamespace=true"]}}) == (
        "syncPolicy:\n  syncOptions:\n    - CreateNamespace=true\n"
    )
    assert dump_yaml({}) == "{}\n"
