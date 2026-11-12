"""A leaf app's ArgoCD sync options: its deploy config's ``syncPolicy``, as four settings.

``deployApp.yaml`` copies the merged ``syncPolicy`` into the leaf Application
as it is (``toYaml``), so ArgoCD reads it with its own rules:

- ``automated`` present (a map, even ``{}``) is auto-sync, unless it says
  ``enabled: false``: ArgoCD's off switch, which keeps the rest of the map.
  Absent (or null) is manual sync, the platform's default for leaves
  (ADR-0022): nothing deploys after a merge until someone syncs.
- ``automated`` that is not a map (``automated: true``) is not an Application
  ArgoCD takes: the CRD refuses it, so the leaf is never created or updated.
  It reads as manual sync, and :func:`automated_problem` says why
  (the ``sync-policy-invalid`` lint).
- ``automated.prune`` and ``automated.selfHeal`` only exist with auto-sync.
- ``syncOptions`` is a list of ``Name=value`` strings.

The deploy config is a stack of Helm value files (``stacks.deploy_config_layers``),
so a higher layer changes the settings through Helm's merge: maps merge key by
key, a list replaces, and ``null`` deletes (``automated: null`` turns auto-sync
off). :func:`policy_override` computes the smallest ``syncPolicy`` a layer must
set to make the effective settings what was asked, and checks the merge gives
exactly that. Other ``syncPolicy`` keys (``retry``, ``managedNamespaceMetadata``,
``automated.allowEmpty``) are kept wherever they are; Wingman does not edit them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from wingman_day2.domain.deploy_config import SYNC_POLICY, auto_sync_enabled, truthy
from wingman_day2.domain.errors import ChangeRefusedError
from wingman_day2.domain.merge import merge_values

AUTOMATED: Final = "automated"
ENABLED: Final = "enabled"
PRUNE: Final = "prune"
SELF_HEAL: Final = "selfHeal"
SYNC_OPTIONS: Final = "syncOptions"

SYNC_OPTION: Final = re.compile(r"^[A-Za-z][A-Za-z0-9]*=[A-Za-z0-9._-]+$")
"""``Name=value``, as ArgoCD's sync options are written."""

KNOWN_SYNC_OPTIONS: Final = (
    "CreateNamespace=true",
    "ServerSideApply=true",
    "PruneLast=true",
    "ApplyOutOfSyncOnly=true",
    "RespectIgnoreDifferences=true",
    "Replace=true",
    "Validate=false",
    "SkipDryRunOnMissingResource=true",
    "FailOnSharedResource=true",
    "PrunePropagationPolicy=foreground",
    "PrunePropagationPolicy=background",
    "PrunePropagationPolicy=orphan",
)
"""The options the web offers as checkboxes; any option of the right shape is accepted."""


@dataclass(frozen=True, slots=True)
class SyncSettings:
    """What a ``syncPolicy`` means for the leaf app."""

    auto_sync: bool = False
    prune: bool = False
    self_heal: bool = False
    sync_options: tuple[str, ...] = ()

    def checked(self) -> SyncSettings:
        """These settings, or a refusal saying what is wrong with them."""
        if not self.auto_sync and (self.prune or self.self_heal):
            raise ChangeRefusedError(
                "prune and self-heal are settings of auto-sync: turn auto-sync on, or leave them "
                "off (a manual sync chooses its own pruning)",
                details={"rule": "sync-without-auto"},
            )
        bad = [option for option in self.sync_options if not SYNC_OPTION.match(option)]
        if bad:
            raise ChangeRefusedError(
                f"sync options are written Name=value (CreateNamespace=true); not {bad[0]!r}",
                details={"rule": "sync-option-invalid", "options": bad},
            )
        repeated = sorted({o for o in self.sync_options if self.sync_options.count(o) > 1})
        if repeated:
            raise ChangeRefusedError(
                f"{repeated[0]} is listed twice in the sync options",
                details={"rule": "sync-option-invalid", "options": repeated},
            )
        return self


PLATFORM_DEFAULT: Final = SyncSettings(sync_options=("CreateNamespace=true",))
"""A new add-on's settings when the team has none to copy: manual sync, create the namespace."""


def sync_settings(policy: object) -> SyncSettings:
    """What a merged ``syncPolicy`` makes ArgoCD do."""
    if not isinstance(policy, Mapping):
        return SyncSettings()
    automated = policy.get(AUTOMATED)
    options = policy.get(SYNC_OPTIONS)
    auto = auto_sync_enabled(automated)
    return SyncSettings(
        auto_sync=auto,
        prune=auto and isinstance(automated, Mapping) and automated.get(PRUNE) is True,
        self_heal=auto and isinstance(automated, Mapping) and automated.get(SELF_HEAL) is True,
        sync_options=tuple(str(o) for o in options) if isinstance(options, list) else (),
    )


def automated_problem(policy: object) -> str | None:
    """Why ArgoCD's Application cannot take this merged ``syncPolicy``; ``None`` when it can.

    The CRD wants ``syncPolicy`` and ``automated`` to be maps and
    ``automated.enabled`` a boolean; any other value makes the API server
    refuse the leaf, so it is neither created nor updated. A ``syncPolicy``
    Go templates read as false (``{}``, ``false``) is not rendered at all.
    """
    if not truthy(policy):
        return None
    if not isinstance(policy, Mapping):
        return f"`syncPolicy: {_yaml(policy)}` is not a map, so ArgoCD refuses the Application"
    return _automated_problem(policy.get(AUTOMATED))


def _automated_problem(automated: object) -> str | None:
    if automated is None:
        return None
    if not isinstance(automated, Mapping):
        return (
            f"`syncPolicy.automated: {_yaml(automated)}` is not a map, so ArgoCD refuses the "
            "Application: write `automated: {}` (with prune and selfHeal inside it) for "
            "auto-sync, or no `automated` for manual sync"
        )
    enabled = automated.get(ENABLED)
    if enabled is not None and not isinstance(enabled, bool):
        return (
            f"`syncPolicy.automated.enabled: {_yaml(enabled)}` is not true or false, so ArgoCD "
            "refuses the Application"
        )
    return None


def _yaml(value: object) -> str:
    return json.dumps(value, default=str)


def _automated(settings: SyncSettings, current: object) -> dict[str, object]:
    automated = dict(current) if isinstance(current, Mapping) else {}
    if automated.get(ENABLED) is not True:
        automated.pop(ENABLED, None)  # ArgoCD's off switch, or a value it refuses
    automated[PRUNE] = settings.prune
    automated[SELF_HEAL] = settings.self_heal
    return automated


def _switched_off(automated: object) -> bool:
    """An ``automated`` map ArgoCD reads as manual sync: ``enabled: false``."""
    return isinstance(automated, Mapping) and automated.get(ENABLED) is False


def full_policy(settings: SyncSettings, current: object = None) -> dict[str, object]:
    """The ``syncPolicy`` of a lowest layer (a team default): exactly ``settings``.

    ``current`` is the file's ``syncPolicy`` today; its other keys are kept,
    and so is an ``automated`` map switched off with ``enabled: false`` when
    the settings are manual sync (what that switch is for). Empty when there
    is nothing to write (manual sync, no options).
    """
    policy = dict(current) if isinstance(current, Mapping) else {}
    if settings.auto_sync:
        policy[AUTOMATED] = _automated(settings, policy.get(AUTOMATED))
    elif not _switched_off(policy.get(AUTOMATED)):
        policy.pop(AUTOMATED, None)
    if settings.sync_options:
        policy[SYNC_OPTIONS] = list(settings.sync_options)
    else:
        policy.pop(SYNC_OPTIONS, None)
    ordered = {k: policy[k] for k in (AUTOMATED, SYNC_OPTIONS) if k in policy}
    return {**ordered, **{k: v for k, v in policy.items() if k not in ordered}}


def effective_policy(layers: Sequence[Mapping[str, object]]) -> object:
    """The ``syncPolicy`` Helm makes of deploy-config ``layers`` (lowest first)."""
    merged = merge_values({}, [(str(i), layer) for i, layer in enumerate(layers)])
    return merged.values.get(SYNC_POLICY)


def policy_override(
    inherited: Sequence[Mapping[str, object]], desired: SyncSettings, current: object = None
) -> dict[str, object]:
    """The ``syncPolicy`` a layer above ``inherited`` must set for ``desired``; ``{}`` for none.

    ``inherited`` are the deploy-config layers below (lowest first);
    ``current`` the layer's own ``syncPolicy`` today, whose other keys are kept.
    """
    below_policy = effective_policy(inherited)
    below = sync_settings(below_policy)
    below_automated = below_policy.get(AUTOMATED) if isinstance(below_policy, Mapping) else None
    policy = dict(current) if isinstance(current, Mapping) else {}
    policy.pop(AUTOMATED, None)
    policy.pop(SYNC_OPTIONS, None)
    if desired.auto_sync:
        if (below.auto_sync, below.prune, below.self_heal) != (
            True,
            desired.prune,
            desired.self_heal,
        ):
            automated = _automated(desired, None)
            if isinstance(below_automated, Mapping) and not below.auto_sync:
                automated[ENABLED] = True  # the layer below switched auto-sync off
            policy[AUTOMATED] = automated
    elif below.auto_sync or _automated_problem(below_automated) is not None:
        policy[AUTOMATED] = None  # delete it: auto-sync, or a value ArgoCD refuses
    if desired.sync_options != below.sync_options:
        policy[SYNC_OPTIONS] = list(desired.sync_options)
    ordered = {k: policy[k] for k in (AUTOMATED, SYNC_OPTIONS) if k in policy}
    override = {**ordered, **{k: v for k, v in policy.items() if k not in ordered}}
    got = sync_settings(effective_policy([*inherited, {SYNC_POLICY: override}]))
    if got != desired:
        raise ChangeRefusedError(
            "the layers below set sync options Wingman cannot override exactly; edit the deploy "
            "config by hand",
            details={"rule": "sync-layering"},
        )
    return override
