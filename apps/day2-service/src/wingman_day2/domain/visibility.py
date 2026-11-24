"""What a viewer may know of day2's destinations, and how their answers name them.

A viewer is a customer (ADR-0067, ADR-0068). Of day2's destinations they
know the tenants' hosted clusters alone: the hub, the UPI clusters, every MCE
hub (a seed's too) and every KV cluster are an admin's. A viewer's lists leave
them out, and naming one answers what an unknown destination answers. Of the
fleet scopes they know the hosted clusters' alone. An admin sees everything.

:class:`Sight` is what one topology shows a viewer:

- a tenant by its bare name: its id, ``hosted:<site>:<env>:<mce>:<name>``,
  carries its MCE (:meth:`Sight.rename`);
- a path in a tenant's own folder from the cluster on,
  ``<cluster>/<chart>/values.yaml`` (:meth:`Sight.path`); any other path, and
  every text, through the redactor of every hidden name (:attr:`Sight.redactor`);
- of a diff, a tenant's own files and the team's files that are about no one
  destination, ``operators/`` and the hosted clusters' fleet defaults
  (:meth:`Sight.file`);
- a merge request or a commit whose words name a tenant or the hosted
  clusters' scope, and nothing hidden (:meth:`Sight.about`);
- a finding about a tenant or about no destination, at a file it may read
  (:meth:`Sight.finding`).
"""

from __future__ import annotations

import functools
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Final

from wingman_core.domain.cluster_kinds import HostedClusterKind, hosted_cluster_kind
from wingman_core.domain.redaction import HIDDEN, Redactor
from wingman_core.domain.users import User
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import (
    ALLOWED_ENVS,
    HUB_NAME,
    ClusterKind,
    ClusterRef,
    DefaultsScope,
)

VIEWER_SCOPE: Final = DefaultsScope.HOSTED_CLUSTERS
"""The one fleet scope a viewer knows: its defaults reach the tenants' clusters."""

_NAME_CHARS: Final = "A-Za-z0-9-"
_Key = tuple[str, str, str, str]


def is_tenant(ref: ClusterRef) -> bool:
    """Whether ``ref`` is a tenant's hosted cluster: not a KV cluster, not on a seed."""
    return (
        ref.kind is ClusterKind.HOSTED
        and hosted_cluster_kind(ref.name, mce=ref.mce) is HostedClusterKind.TENANT
    )


def sees_destination(user: User, ref: ClusterRef) -> bool:
    """Whether ``user`` may know of the destination ``ref``: a viewer, of a tenant's alone."""
    return user.is_admin or is_tenant(ref)


def sees_scope(user: User, scope: DefaultsScope) -> bool:
    """Whether ``user`` may know of the fleet scope: a viewer, of the hosted clusters' alone."""
    return user.is_admin or scope is VIEWER_SCOPE


def real_path(ref: ClusterRef, shown: str) -> str:
    """The repo path a viewer's ``shown`` path of the tenant ``ref``'s stack stands for.

    The inverse of :meth:`Sight.path` and of the redactor for that stack: its
    own folder's files start at the cluster's name, and its MCE layer reads
    ``[hidden]`` where the MCE's name is.
    """
    name, _, rest = shown.partition("/")
    if name == ref.name:
        folder = layout.cluster_dir(ref)
        return f"{folder}/{rest}" if rest else str(folder)
    return shown.replace(HIDDEN, ref.mce)


@functools.lru_cache(maxsize=32)
def _pattern(words: frozenset[str]) -> re.Pattern[str] | None:
    """The redactor's whole-token match: longest first, case ignored."""
    if not words:
        return None
    alternatives = "|".join(re.escape(w) for w in sorted(words, key=lambda w: (-len(w), w)))
    return re.compile(rf"(?<![{_NAME_CHARS}])(?:{alternatives})(?![{_NAME_CHARS}])", re.IGNORECASE)


def _found(words: frozenset[str], text: str) -> set[str]:
    """The ``words`` in ``text`` as whole tokens, lowercase; a longer one hides those inside it."""
    pattern = _pattern(words)
    return set() if pattern is None else {m.group(0).lower() for m in pattern.finditer(text)}


@dataclass(frozen=True, slots=True)
class Sight:
    """What a viewer may know of a topology's destinations. Build it with :meth:`of`."""

    folders: Mapping[_Key, str] = field(default_factory=dict)
    """Each tenant's ``(site, env, mce, name)``: its folder, and its bare name."""
    names: Mapping[str, str] = field(default_factory=dict)
    """Each tenant's id: its bare name."""
    redactor: Redactor = field(default_factory=Redactor)
    """Every hidden name: each MCE folder's, the hub's and its Argo CDs', each UPI and KV one's."""
    context: Mapping[str, frozenset[str]] = field(default_factory=dict)
    """Each tenant's name and id, lowercase: the MCE folders its words may name."""
    visible_scope: frozenset[str] = frozenset()
    hidden: frozenset[str] = frozenset()
    """Hidden ids, hidden names that are not an MCE folder's, and the hidden scopes' words."""
    mce_folders: frozenset[str] = frozenset()
    words: frozenset[str] = frozenset()
    """All of the above: what :meth:`about` looks for."""

    @classmethod
    def of(cls, refs: Iterable[ClusterRef], scopes: Mapping[DefaultsScope, str]) -> Sight:
        """From every destination of a topology and the words each fleet scope is named by."""
        tenants: list[ClusterRef] = []
        others: list[ClusterRef] = []
        for ref in refs:
            (tenants if is_tenant(ref) else others).append(ref)
        context: dict[str, set[str]] = defaultdict(set)
        for ref in tenants:
            for word in (ref.name, ref.id):
                context[word.lower()].add(ref.mce.lower())
        folders = {r.mce for r in (*tenants, *others) if r.mce}
        named = {HUB_NAME, *(n for r in others for n in (r.name, r.argo_instance))}
        named -= folders | {r.name for r in tenants}
        scope_words = {
            scope: (scopes.get(scope, ""), str(layout.defaults_dir(scope)))
            for scope in DefaultsScope
        }
        hidden_scopes = {w for s, ws in scope_words.items() if s is not VIEWER_SCOPE for w in ws}
        hidden_ids = {r.id for r in others if r.kind is not ClusterKind.HUB}
        visible_scope = frozenset(w.lower() for w in scope_words[VIEWER_SCOPE] if w)
        hidden = frozenset(w.lower() for w in (*hidden_ids, *named, *hidden_scopes) if w)
        mce_folders = frozenset(f.lower() for f in folders)
        return cls(
            folders={(r.site, r.env, r.mce, r.name): r.name for r in tenants},
            names={r.id: r.name for r in tenants},
            redactor=Redactor.of([*folders, *named]),
            context={w: frozenset(m) for w, m in context.items()},
            visible_scope=visible_scope,
            hidden=hidden,
            mce_folders=mce_folders,
            words=frozenset({*context, *visible_scope, *hidden, *mce_folders}),
        )

    @property
    def tenant_names(self) -> frozenset[str]:
        """Every tenant's bare name."""
        return frozenset(self.names.values())

    def path(self, path: str) -> str | None:
        """``path`` from the cluster on when it is in a tenant's own folder; ``None`` otherwise."""
        parts = path.split("/")
        if len(parts) < 6 or (parts[0], parts[3]) != (layout.SITES, layout.MCES):
            return None
        key = (parts[1], parts[2], parts[4], parts[5])
        return "/".join(parts[5:]) if key in self.folders else None

    def rename(self, value: str) -> str:
        """``value`` as a viewer reads it: a tenant's id its name, a path in its folder from it."""
        if value in self.names:
            return self.names[value]
        own = self.path(value)
        return value if own is None else own

    def file(self, path: str) -> str | None:
        """How a viewer reads ``path`` of a diff or a finding; ``None`` for one they may not read.

        A tenant's own file, from its folder on; a file of the team's own, at its
        path: ``operators/…`` (the Sig values) and a hosted clusters' fleet
        default's (whose ``values-<name>.yaml`` is a tenant's or an env's).
        Every other file is a destination's they may not know of, or a scope's.
        """
        own = self.path(path)
        if own is not None:
            return own
        parts = path.split("/")
        if parts[0] == layout.OPERATORS and len(parts) > 1:
            return path
        fleet = str(layout.defaults_dir(VIEWER_SCOPE)).split("/")
        if parts[:2] != fleet or len(parts) < 3 or parts[2] == layout.EXCLUSIONS_FILE:
            return None
        if len(parts) > 3 and parts[3].startswith("values-") and parts[3].endswith(".yaml"):
            name = parts[3].removeprefix("values-").removesuffix(".yaml")
            return path if name in ALLOWED_ENVS or name in self.tenant_names else None
        return path

    def finding(self, cluster: str, path: str) -> bool:
        """Whether a viewer reads a finding about ``cluster`` (an id) at ``path``, both optional."""
        return (not cluster or cluster in self.names) and (not path or self.file(path) is not None)

    def about(self, text: str) -> bool:
        """Whether a merge request's or a commit's words are a viewer's to read.

        They are when they name a tenant (by name or id) or the hosted clusters'
        scope, and nothing hidden: no other destination by its id or name, no
        other scope, and no MCE folder but those of the tenants they name (a
        tenant's id, folder and Argo CD carry its MCE). Whole tokens, case
        ignored, as the redactor matches.
        """
        found = _found(self.words, text)
        tenants = found & self.context.keys()
        if not tenants and not found & self.visible_scope:
            return False
        theirs = {m for word in tenants for m in self.context[word]}
        return not (found & self.hidden or (found & self.mce_folders) - theirs)
