"""The checks Wingman runs on a team repo, before an MR and on demand (ADR-0023).

``lint_tree`` and ``lint_exclusions`` are ``render_chain.py``'s
``lint_sigs_tree`` and ``lint_exclusions`` (gitops-day2-prod @ 979e306), rule
for rule, minus the migration-window checks of the legacy marker files.
``PlannedApp`` duplicates are its "DUPLICATE app generated" failure.
``lint_leaf`` and :func:`upgrade_check` are Wingman's own.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from wingman_core.domain.git import RepoPath
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import (
    ALLOWED_ENVS,
    IN_CLUSTER,
    ClusterKind,
    ClusterRef,
    DefaultsScope,
)
from wingman_day2.domain.day1 import Day1Index
from wingman_day2.domain.deploy_config import (
    TARGET_REVISION,
    LeafApplication,
    miscased_repourl_keys,
)
from wingman_day2.domain.exclusions import EXCLUSIONS_KEY
from wingman_day2.domain.findings import Finding, Rule, error, info, warning
from wingman_day2.domain.platform import PlannedApp, TeamPlan
from wingman_day2.domain.stacks import Layer, LayerRole
from wingman_day2.domain.teams import TeamRepo
from wingman_day2.domain.tree import RepoTree
from wingman_day2.domain.versions import VersionFile, read_version_file
from wingman_day2.domain.yaml_values import YamlProblem, parse_yaml

_SITES = RepoPath.of(layout.SITES)


def _envs_allowed() -> str:
    return ", ".join(sorted(ALLOWED_ENVS))


def _day1_version(
    team: str, entry_version: VersionFile | None, path: RepoPath, needed_by: RepoPath
) -> list[Finding]:
    where = {"team": team, "path": str(needed_by)}
    if entry_version is None:
        return [
            error(
                Rule.DAY1_VERSION_MISSING,
                f"{needed_by}: no day1 version file at {path}. Every MCE and hosted-cluster "
                "folder resolves its OCP version from one; either day1 has not provisioned this "
                "cluster, or the folder is not a cluster (a stray folder becomes a phantom app).",
                **where,
            )
        ]
    if entry_version.mastertag is None:
        return [error(Rule.MASTERTAG_MISSING, f"{path}: no top-level mastertag", **where)]
    if entry_version.problem:
        return [error(Rule.MASTERTAG_INVALID, f"{path}: {entry_version.problem}", **where)]
    return []


def _legacy_markers(tree: RepoTree) -> bool:
    for file in tree.files:
        if not file.startswith("mces/") or any(s.startswith(".") for s in file.split("/")):
            continue
        depth = file.count("/")
        if (file.endswith("/mce.yaml") and depth >= 2) or (
            file.endswith("/hc.yaml") and depth >= 3
        ):
            return True
    return False


def lint_tree(repo: TeamRepo, day1: Day1Index) -> list[Finding]:
    """render_chain's ``lint_sigs_tree``: envs, day1 parity, UPI names and version files."""
    tree, team = repo.tree, repo.team
    found: list[Finding] = []
    if _legacy_markers(tree):
        found.append(
            error(
                Rule.LEGACY_LAYOUT,
                "legacy mces/ layout found: a day1 version file cannot be located without the "
                "sites/<site>/ path segment; finish the sites/ migration first",
                team=team,
                path="mces",
            )
        )
    mce_names: set[str] = set()
    hc_names: set[str] = set()
    for site in tree.subdirs(_SITES):
        for env in tree.subdirs(_SITES.child(site)):
            mces = _SITES.child(site, env, layout.MCES)
            for mce in tree.subdirs(mces):
                mce_names.add(mce)
                folder = mces.child(mce)
                if env not in ALLOWED_ENVS:
                    found.append(
                        error(
                            Rule.ENV_NOT_ALLOWED,
                            f"{folder}: env folder '{env}' is not one of {_envs_allowed()}",
                            team=team,
                            path=str(folder),
                        )
                    )
                entry = day1.mce(site, mce)
                found += _day1_version(
                    team,
                    entry.version if entry else None,
                    layout.day1_mce_version_file(site, mce),
                    folder,
                )
                for name in tree.subdirs(folder):
                    if name == IN_CLUSTER:
                        continue
                    hc_names.add(name)
                    hosted = day1.hosted_cluster(site, mce, name)
                    found += _day1_version(
                        team,
                        hosted.version if hosted else None,
                        layout.day1_hosted_cluster_file(site, mce, name),
                        folder.child(name),
                    )
    for site in tree.subdirs(_SITES):
        for env in tree.subdirs(_SITES.child(site)):
            upi = _SITES.child(site, env, layout.UPI)
            for name in tree.subdirs(upi):
                found += _lint_upi(repo, upi.child(name), env, name, mce_names | hc_names)
    return found


def _lint_upi(
    repo: TeamRepo, folder: RepoPath, env: str, name: str, taken: set[str]
) -> list[Finding]:
    team = repo.team
    where = {"team": team, "path": str(folder)}
    found: list[Finding] = []
    if env not in ALLOWED_ENVS:
        found.append(
            error(
                Rule.ENV_NOT_ALLOWED,
                f"{folder}: env folder '{env}' is not one of {_envs_allowed()}",
                **where,
            )
        )
    if name == IN_CLUSTER:
        found.append(
            error(
                Rule.UPI_NAME_IN_CLUSTER,
                f"{folder}: a UPI cluster cannot be named {IN_CLUSTER}: that is every Argo's name "
                "for its own cluster, and the operators chart would render it as an MCE hub",
                **where,
            )
        )
    elif name in taken:
        found.append(
            error(
                Rule.UPI_NAME_REUSED,
                f"{folder}: UPI folder {name!r} reuses an MCE or hosted-cluster name; cluster "
                "names are flat and global, so one name would mean two clusters",
                **where,
            )
        )
    path = folder.child(layout.VERSION_FILE)
    text = repo.files.get(str(path))
    if text is None:
        return found
    version = read_version_file(text, path=str(path))
    where = {"team": team, "path": str(path)}
    if version.yaml_problem is not None:
        found.append(error(Rule.UPI_VERSION_FILE_INVALID, version.yaml_problem.message, **where))
    elif version.extra_keys or (version.mastertag is None and version.problem):
        found.append(
            error(
                Rule.UPI_VERSION_FILE_INVALID,
                f"{path}: a UPI version file carries `mastertag` and nothing else (found "
                f"{', '.join(version.extra_keys) or 'no mastertag'}); it is loaded as a Helm "
                "value file, so every other key becomes a chart value",
                **where,
            )
        )
    elif version.problem:
        found.append(error(Rule.MASTERTAG_INVALID, f"{path}: {version.problem}", **where))
    return found


def _known_targets(tree: RepoTree) -> dict[DefaultsScope, tuple[str, list[str]]]:
    mces: set[str] = set()
    hosted: set[str] = set()
    upis: set[str] = set()
    for site in tree.subdirs(_SITES):
        for env in tree.subdirs(_SITES.child(site)):
            for mce in tree.subdirs(_SITES.child(site, env, layout.MCES)):
                mces.add(mce)
                hosted.update(tree.subdirs(_SITES.child(site, env, layout.MCES, mce)))
            upis.update(tree.subdirs(_SITES.child(site, env, layout.UPI)))
    return {
        DefaultsScope.MCES: ("MCE", sorted(mces)),
        DefaultsScope.HOSTED_CLUSTERS: ("hosted cluster", sorted(hosted - {IN_CLUSTER})),
        DefaultsScope.UPI: ("UPI cluster", sorted(upis)),
    }


def lint_exclusions(repo: TeamRepo) -> list[Finding]:
    """render_chain's ``lint_exclusions``: rules 0-3 on ``defaults/<scope>/exclusions.yaml``."""
    tree, team = repo.tree, repo.team
    found: list[Finding] = []
    hub_file = layout.exclusions_file(DefaultsScope.HUB)
    if tree.is_file(hub_file):
        found.append(
            error(
                Rule.EXCLUSIONS_HUB,
                f"{hub_file}: there are no hub exclusions. The hub is one cluster and its charts "
                "never pass through the operators chart; to stop deploying a hub chart, delete "
                "its folder.",
                team=team,
                path=str(hub_file),
            )
        )
    for scope, (kind, known) in _known_targets(tree).items():
        path = layout.exclusions_file(scope)
        text = repo.files.get(str(path))
        if text is None:
            continue
        found += _lint_exclusion_file(team, tree, scope, path, text, kind, known)
    return found


def _lint_exclusion_file(
    team: str,
    tree: RepoTree,
    scope: DefaultsScope,
    path: RepoPath,
    text: str,
    kind: str,
    known: list[str],
) -> list[Finding]:
    def fail(rule: Rule, message: str) -> Finding:
        return error(rule, f"{path}: {message}", team=team, path=str(path))

    doc, problem = parse_yaml(text, path=str(path))
    if problem is not None:
        return [fail(Rule.EXCLUSIONS_SCHEMA, problem.message)]
    doc = {} if doc is None else doc
    if not isinstance(doc, dict):
        return [
            fail(
                Rule.EXCLUSIONS_SCHEMA,
                f"the top level must be a mapping with the single key `{EXCLUSIONS_KEY}`",
            )
        ]
    found: list[Finding] = []
    stray = sorted(str(k) for k in doc if k != EXCLUSIONS_KEY)
    if stray:
        found.append(
            fail(
                Rule.EXCLUSIONS_SCHEMA,
                f"`{EXCLUSIONS_KEY}` must be the only top-level key; found {stray}. Every other "
                "key is merged into the operators chart's values as a real chart value.",
            )
        )
    entries = doc.get(EXCLUSIONS_KEY)
    if entries is None:
        return found
    if not isinstance(entries, dict):
        return [
            *found,
            fail(Rule.EXCLUSIONS_SCHEMA, f"`{EXCLUSIONS_KEY}` must map <chart> to [{kind} names]"),
        ]
    charts = tree.subdirs(layout.defaults_dir(scope))
    for chart, names in sorted(entries.items(), key=lambda item: str(item[0])):
        if chart not in charts:
            found.append(
                fail(
                    Rule.EXCLUSIONS_UNKNOWN_CHART,
                    f"key {chart!r} is not a chart folder in {layout.defaults_dir(scope)}/ (have: "
                    f"{', '.join(charts) or 'none'}): it excludes nothing, and the chart keeps "
                    "deploying to the cluster that asked to opt out",
                )
            )
        if names is None:
            continue
        if not isinstance(names, list):
            found.append(
                fail(
                    Rule.EXCLUSIONS_SCHEMA,
                    f"{EXCLUSIONS_KEY}.{chart} must be a list of {kind} names",
                )
            )
            continue
        for name in names:
            if not isinstance(name, str):
                found.append(
                    fail(
                        Rule.EXCLUSIONS_SCHEMA,
                        f"{EXCLUSIONS_KEY}.{chart} entry {name!r} is not a {kind} name",
                    )
                )
            elif name not in known:
                found.append(
                    fail(
                        Rule.EXCLUSIONS_UNKNOWN_TARGET,
                        f"{name!r} under {EXCLUSIONS_KEY}.{chart} is not a {kind} in this repo "
                        f"(have: {', '.join(known) or 'none'}): no exclude is emitted and {chart} "
                        "still deploys fleet-wide",
                    )
                )
    return found


def lint_team(repo: TeamRepo, day1: Day1Index, plan: TeamPlan) -> list[Finding]:
    """Every structural check on one team repo (no deploy-config contents needed)."""
    return [*lint_tree(repo, day1), *lint_exclusions(repo), *plan.duplicates()]


def lint_leaf(
    app: PlannedApp,
    docs: Sequence[tuple[Layer, Mapping[str, object] | None, YamlProblem | None]],
    leaf: LeafApplication,
    tree: RepoTree,
) -> list[Finding]:
    """Wingman's checks on one app's deploy config: ``repourl`` casing, pins, YAML.

    ``docs`` are the app's existing deploy-config files, parsed (``None`` when absent).
    """
    where = {"team": app.team, "cluster": app.ref.id, "chart": app.chart}
    found: list[Finding] = []
    miscased: list[str] = []
    pins = tree.subdirs(layout.ocp_versions_dir(app.chart))
    for layer, doc, problem in docs:
        if problem is not None:
            found.append(error(Rule.YAML_INVALID, problem.message, path=str(layer.path), **where))
            continue
        if doc is None:
            continue
        for key in miscased_repourl_keys(doc):
            miscased.append(str(layer.path))
            found.append(
                warning(
                    Rule.REPOURL_MISCASED,
                    f"{layer.path} sets `{key}`; the platform reads only lowercase `repourl`, so "
                    "this key is ignored and does not set the chart repo",
                    path=str(layer.path),
                    **where,
                )
            )
        if TARGET_REVISION in doc and layer.role is LayerRole.FLEET and pins:
            found.append(
                warning(
                    Rule.FLEET_PIN_OVERRIDES_OCP_VERSIONS,
                    f"{layer.path} sets targetRevision, which overrides every ocp-versions/ pin "
                    f"of {app.chart} ({', '.join(pins)})",
                    path=str(layer.path),
                    **where,
                )
            )
        if (
            TARGET_REVISION in doc
            and layer.role is LayerRole.CLUSTER
            and app.ref.kind is not ClusterKind.HUB
        ):
            found.append(
                info(
                    Rule.EMERGENCY_PIN,
                    f"{layer.path} pins targetRevision {doc[TARGET_REVISION]!r} for this cluster "
                    "only: an emergency pin that detaches it from the team default and from "
                    "ocp-versions/ pins until removed",
                    path=str(layer.path),
                    **where,
                )
            )
    if not leaf.repo_url:
        hint = f" ({', '.join(miscased)} use a miscased key)" if miscased else ""
        found.append(
            error(
                Rule.REPOURL_MISSING,
                f"no layer of {app.chart}'s deploy config sets a lowercase `repourl`{hint}: "
                f"ArgoCD renders {leaf.name} with an empty repoURL",
                path=str(app.folder),
                **where,
            )
        )
    if pins and app.ocp_version and app.ocp_version not in pins:
        found.append(
            warning(
                Rule.OCP_VERSION_PIN_MISSING,
                f"{app.chart} is pinned per OCP version ({', '.join(pins)}) but has no "
                f"{layout.ocp_version_dir(app.chart, app.ocp_version)}/ for this cluster's "
                f"{app.ocp_version}: it falls back to the team default",
                path=str(layout.ocp_versions_dir(app.chart)),
                **where,
            )
        )
    return found


def upgrade_check(
    apps: Iterable[PlannedApp], tree_of: Mapping[str, RepoTree], to: str
) -> list[Finding]:
    """Charts that would silently fall back to their team default if a cluster moved to ``to``.

    ``ocp-versions/`` folders are keyed by the full version, so each must exist
    before day1 flips ``mastertag``. ``tree_of`` maps each team to its tree.
    """
    found = []
    for app in apps:
        pins = tree_of[app.team].subdirs(layout.ocp_versions_dir(app.chart))
        if pins and to not in pins:
            found.append(
                warning(
                    Rule.OCP_VERSION_PIN_MISSING,
                    f"{app.team}/{app.chart} is pinned per OCP version ({', '.join(pins)}); create "
                    f"{layout.ocp_version_dir(app.chart, to)}/ before the cluster moves to {to}, "
                    "or it falls back to the team default",
                    team=app.team,
                    path=str(layout.ocp_versions_dir(app.chart)),
                    cluster=app.ref.id,
                    chart=app.chart,
                )
            )
    return found


def position_conflicts(refs_by_team: Mapping[str, Iterable[ClusterRef]]) -> list[Finding]:
    """Cluster names placed at more than one position across team repos."""
    positions: dict[tuple[bool, str], set[ClusterRef]] = defaultdict(set)
    for refs in refs_by_team.values():
        for ref in refs:
            positions[(ref.kind is ClusterKind.MCE, ref.name)].add(ref)
    found = []
    for (_, name), refs in sorted(positions.items(), key=lambda item: item[0][1]):
        if len(refs) > 1:
            ids = sorted(r.id for r in refs)
            found.append(
                warning(
                    Rule.CLUSTER_POSITION_CONFLICT,
                    f"{name} is placed at {len(ids)} positions across team repos "
                    f"({', '.join(ids)}); cluster names are global, so all but one are wrong",
                    cluster=ids[0],
                )
            )
    return found
