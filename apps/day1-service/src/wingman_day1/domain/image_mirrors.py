"""A flavor's image mirrors: the cluster's own, and whether the MCE's are kept (ADR-0063).

The hostedclusters-setup chart builds the HostedCluster's
``imageContentSources`` from two lists of ``{source, mirrors}``: the MCE
values layer's ``defaultImageContentSources`` and the cluster file's own
``imageContentSources``. It puts them together, merges the entries of one
``source`` (their mirrors joined) and sorts them by source. A cluster file
with ``disableIdmsMerge: true`` gets only its own list; the MCE's are dropped.

Two optional template inputs carry them, and the shared template writes
each to its key only when it is given:

=========================  =======================
template input             cluster-file key
=========================  =======================
``image_content_sources``  ``imageContentSources``
``disable_idms_merge``     ``disableIdmsMerge``
=========================  =======================

Absent, nothing is written and the MCE's mirrors apply, as before. Both are
lockable (``locks.LOCKABLE``), so drift and a flavor's per-cluster merge
requests compare and write them as the chart reads them: a list by its
merged, sorted entries (an absent key is no entries), ``disableIdmsMerge``
by Go's truth (an absent key keeps the MCE's mirrors).

A cluster with ``disable_idms_merge`` and no entries of its own would have
no mirrors at all, so it is refused, at a flavor's save and at a create.
And because each specs project has its own ``cluster-template.j2``, a
flavor that gives mirrors is refused while that template does not read
them, and a create whose rendered file does not hold them as given is
refused: an older template never drops them silently.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Final, cast

from wingman_day1.domain.errors import RenderError
from wingman_day1.domain.input_paths import MISSING
from wingman_day1.domain.template import analyze_template

IMAGE_MIRRORS: Final = "image_content_sources"
"""The cluster's own mirrors: ``[{source, mirrors: [...]}]``."""
DROP_MCE_MIRRORS: Final = "disable_idms_merge"
"""``true``: only the cluster's own mirrors; the MCE's ``defaultImageContentSources`` go."""
MIRRORS_FILE_KEY: Final = "imageContentSources"
DROP_FILE_KEY: Final = "disableIdmsMerge"
MIRROR_FILE_KEYS: Final = (MIRRORS_FILE_KEY, DROP_FILE_KEY)

UPGRADE_GUIDE: Final = "docs/upgrade/3.44-to-3.45.md"
"""Where an operator finds the template lines (ADR-0063)."""
_ENTRY_KEYS: Final = frozenset({"source", "mirrors"})
_SHOWN: Final = 120

Mirrors = tuple[tuple[str, tuple[str, ...]], ...]


# ── The inputs ───────────────────────────────────────────────────────────────


def _address_problem(value: object, *, what: str) -> str | None:
    """Why ``value`` is not an image source or mirror (the safe-value rule is checked apart)."""
    if not isinstance(value, str) or not value:
        return f"give {what}"
    if any(c.isspace() for c in value):
        return f"{value!r} has a space; give {what}"
    if "://" in value:
        return f"{value!r} is a URL; give the registry path without its scheme"
    if value.startswith("-"):
        return f"{value!r} starts with '-'; give {what}"
    return None


def _mirror_problems(at: str, mirrors: object) -> list[str]:
    if not isinstance(mirrors, list) or not mirrors:
        return [f"{at}.mirrors: give at least one mirror, like mirror.example.com/ocp/release"]
    problems: list[str] = []
    seen: set[str] = set()
    for index, mirror in enumerate(cast("list[object]", mirrors)):
        problem = _address_problem(mirror, what="a mirror, like mirror.example.com/ocp/release")
        if problem is None and mirror in seen:
            problem = f"{mirror} is listed twice"
        if problem is not None:
            problems.append(f"{at}.mirrors[{index}]: {problem}")
        seen.add(str(mirror))
    return problems


def _entry_problems(index: int, entry: object, sources: dict[str, int]) -> list[str]:
    at = f"{IMAGE_MIRRORS}[{index}]"
    if not isinstance(entry, Mapping):
        return [f"{at}: an entry is a source and its mirrors, like {{source: ..., mirrors: [...]}}"]
    found = cast("Mapping[str, object]", entry)
    problems = [
        f"{at}: {key} is not a key of an entry; an entry has a source and its mirrors"
        for key in sorted(set(found) - _ENTRY_KEYS, key=str)
    ]
    source = found.get("source")
    problem = _address_problem(
        source, what="the registry or repository images come from, like registry.example.com/ocp"
    )
    if problem is None and str(source) in sources:
        problem = (
            f"{source} is listed twice (also {IMAGE_MIRRORS}[{sources[str(source)]}]); give all "
            "its mirrors in one entry"
        )
    if problem is not None:
        problems.append(f"{at}.source: {problem}")
    else:
        sources[str(source)] = index
    return problems + _mirror_problems(at, found.get("mirrors"))


def mirror_problems(values: Mapping[str, object]) -> list[str]:
    """Why the image mirror inputs in ``values`` cannot be used; empty when they can.

    Absent inputs are fine. Each entry has a source and at least one mirror,
    without spaces or a URL scheme; a source is listed once, a mirror once
    per entry. ``disable_idms_merge`` is true or false, and true needs
    entries of its own. Values are pasted into YAML, so ``check_inputs``
    checks them as text too.
    """
    entries = values.get(IMAGE_MIRRORS, MISSING)
    problems: list[str] = []
    if entries is not MISSING:
        if isinstance(entries, list):
            sources: dict[str, int] = {}
            for index, entry in enumerate(cast("list[object]", entries)):
                problems += _entry_problems(index, entry, sources)
        else:
            problems.append(
                f"{IMAGE_MIRRORS}: give a list of entries, each a source and its mirrors"
            )
    drop = values.get(DROP_MCE_MIRRORS, MISSING)
    if drop is not MISSING and not isinstance(drop, bool):
        problems.append(
            f"{DROP_MCE_MIRRORS}: give true or false (true keeps only the cluster's own mirrors); "
            f"it is {drop!r}"
        )
    elif drop is True and entries in (MISSING, [], None):
        problems.append(
            f"{DROP_MCE_MIRRORS}: true drops the MCE's default mirrors, and "
            f"{IMAGE_MIRRORS} gives none, so the cluster would have no image mirrors at all; "
            "give the cluster's own mirrors, or keep the MCE's"
        )
    return problems


def mirror_lock_problem(name: str, values: Mapping[str, object]) -> str | None:
    """Why a lock on mirror input ``name`` fixes no usable value; ``None`` when it does.

    Also ``None`` for any other input, and for one ``values`` does not set
    (the lock rules say so). A lock that breaks a rule is not enforced.
    """
    if name not in (IMAGE_MIRRORS, DROP_MCE_MIRRORS) or name not in values:
        return None
    broken = [p for p in mirror_problems(values) if p.startswith(name)]
    if not broken:
        return None
    return f"locked_paths: {name} is locked to a value that breaks a rule: {broken[0]}"


def given_mirror_inputs(values: Mapping[str, object]) -> list[str]:
    """The mirror inputs ``values`` gives that change the cluster file."""
    given: list[str] = []
    if values.get(IMAGE_MIRRORS) not in (None, []):
        given.append(IMAGE_MIRRORS)
    if values.get(DROP_MCE_MIRRORS) is True:
        given.append(DROP_MCE_MIRRORS)
    return given


def mirror_template_problems(values: Mapping[str, object], template: str) -> list[str]:
    """Each mirror input ``values`` gives that the shared ``template`` does not read.

    Such a flavor would create clusters without its mirrors, so it is not
    saved until the specs project's template reads them. An empty template
    (no ``cluster-template.j2``, or a spec read without it) and one that is
    not valid Jinja are left to the create, which refuses both.
    """
    given = given_mirror_inputs(values)
    if not given or not template.strip():
        return []
    try:
        read = {field.name for field in analyze_template(template, include_reserved=True)}
    except RenderError:
        return []
    return [
        f"{name}: the specs project's cluster-template.j2 does not read this input, so a "
        f"cluster created from this flavor would not get it; add the template lines in "
        f"{UPGRADE_GUIDE} (ADR-0063)"
        for name in given
        if name not in read
    ]


# ── The chart's view ─────────────────────────────────────────────────────────


def merged(value: object) -> Mirrors | None:
    """A mirror list as the chart uses it: one entry per source, mirrors joined, by source.

    No value is no entries. ``None`` for a value of another shape, which
    never equals a list.
    """
    if value is MISSING or value is None:
        return ()
    if not isinstance(value, list):
        return None
    joined: dict[str, list[str]] = {}
    for entry in cast("list[object]", value):
        if not isinstance(entry, Mapping):
            return None
        found = cast("Mapping[str, object]", entry)
        source, mirrors = found.get("source"), found.get("mirrors", [])
        if not isinstance(source, str) or not isinstance(mirrors, list):
            return None
        names = joined.setdefault(source, [])
        for mirror in cast("list[object]", mirrors):
            if not isinstance(mirror, str):
                return None
            if mirror not in names:
                names.append(mirror)
    return tuple((source, tuple(joined[source])) for source in sorted(joined))


def drops_mce_mirrors(value: object) -> bool:
    """Whether a ``disableIdmsMerge`` value drops the MCE's mirrors: Go's truth, as Helm's."""
    if value is MISSING or value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, (str, list, dict)):
        return len(cast("Sequence[object]", value)) > 0
    return True


def mirrors_held(file_key: str, locked: object, have: object) -> bool:
    """Whether a cluster file's value at ``file_key`` gives what the flavor locks."""
    if file_key == DROP_FILE_KEY:
        return drops_mce_mirrors(have) == (locked is True)
    want = merged(locked)
    return want is not None and want == merged(have)


def show_mirrors(value: object) -> str:
    """A mirror value as a problem or an MR description shows it: ``source → mirror, ...``."""
    if value is MISSING:
        return "(absent)"
    entries = merged(value)
    if entries is None or not entries:
        text = "none" if entries == () else json.dumps(value, default=str)
    else:
        text = "; ".join(f"{source} → {', '.join(mirrors)}" for source, mirrors in entries)
    return text if len(text) <= _SHOWN else f"{text[: _SHOWN - 3]}..."


def unrendered_mirrors(inputs: Mapping[str, object], rendered: Mapping[str, object]) -> list[str]:
    """Each mirror input the rendered file does not hold as given.

    Checked only for the inputs given, so a flavor without mirrors renders
    as before whatever the template does.
    """
    problems: list[str] = []
    hint = (
        f"the specs project's cluster-template.j2 must render it as given (the lines are in "
        f"{UPGRADE_GUIDE}, ADR-0063)"
    )
    if IMAGE_MIRRORS in inputs:
        have = rendered.get(MIRRORS_FILE_KEY, MISSING)
        if not mirrors_held(MIRRORS_FILE_KEY, inputs[IMAGE_MIRRORS], have):
            problems.append(
                f"{MIRRORS_FILE_KEY}: the template wrote {show_mirrors(have)} for {IMAGE_MIRRORS} "
                f"{show_mirrors(inputs[IMAGE_MIRRORS])}; {hint}"
            )
    if DROP_MCE_MIRRORS in inputs:
        have = rendered.get(DROP_FILE_KEY, MISSING)
        if not mirrors_held(DROP_FILE_KEY, inputs[DROP_MCE_MIRRORS], have):
            wrote = "(absent)" if have is MISSING else json.dumps(have, default=str)
            problems.append(
                f"{DROP_FILE_KEY}: the template wrote {wrote} for {DROP_MCE_MIRRORS} "
                f"{json.dumps(inputs[DROP_MCE_MIRRORS], default=str)}; {hint}"
            )
    return problems
