"""Sync options: what a syncPolicy means, the policy a layer writes, and checks (ADR-0043)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wingman_day2.domain.clusters import ClusterRef
from wingman_day2.domain.deploy_config import leaf_application
from wingman_day2.domain.errors import ChangeRefusedError
from wingman_day2.domain.sync_policy import (
    KNOWN_SYNC_OPTIONS,
    PLATFORM_DEFAULT,
    SyncSettings,
    effective_policy,
    full_policy,
    policy_override,
    sync_settings,
)

AUTO = SyncSettings(auto_sync=True, prune=False, self_heal=True)
MANUAL = SyncSettings(sync_options=("CreateNamespace=true",))


def test_automated_present_is_auto_sync_even_when_empty() -> None:
    assert sync_settings({"automated": {}}) == SyncSettings(auto_sync=True)
    assert sync_settings({"automated": {"prune": True, "selfHeal": True}}) == SyncSettings(
        True, True, True
    )
    assert sync_settings({"syncOptions": ["CreateNamespace=true"]}) == MANUAL
    assert sync_settings(None) == SyncSettings() == sync_settings("junk")
    # ArgoCD's leaf follows the same rule: an empty automated map is auto-sync.
    leaf = leaf_application(
        {"repourl": "x", "syncPolicy": {"automated": {}}}, team="t", chart="c", ref=ClusterRef.hub()
    )
    assert leaf.auto_sync


def test_a_team_default_policy_keeps_other_keys_and_writes_both_auto_settings() -> None:
    current = {"syncOptions": ["A=b"], "retry": {"limit": 2}, "automated": {"allowEmpty": True}}
    policy = full_policy(SyncSettings(True, True, False, ("CreateNamespace=true",)), current)
    assert policy == {
        "automated": {"allowEmpty": True, "prune": True, "selfHeal": False},
        "syncOptions": ["CreateNamespace=true"],
        "retry": {"limit": 2},
    }
    assert list(policy) == ["automated", "syncOptions", "retry"]
    assert full_policy(SyncSettings(), current) == {"retry": {"limit": 2}}
    assert full_policy(SyncSettings()) == {}


def test_a_fleet_override_is_minimal_and_null_turns_auto_sync_off() -> None:
    team = {"syncPolicy": {"automated": {"selfHeal": True, "prune": False}}}
    assert policy_override([team], AUTO) == {}
    assert policy_override([team], SyncSettings()) == {"automated": None}
    assert policy_override([team], MANUAL) == {
        "automated": None,
        "syncOptions": ["CreateNamespace=true"],
    }
    assert policy_override([{}], AUTO) == {"automated": {"prune": False, "selfHeal": True}}
    with_options = {"syncPolicy": {"syncOptions": ["CreateNamespace=true"]}}
    assert policy_override([with_options], SyncSettings()) == {"syncOptions": []}
    # The layer's own other keys stay.
    assert policy_override([{}], SyncSettings(), {"retry": {"limit": 1}, "automated": {}}) == {
        "retry": {"limit": 1}
    }


_settings = st.builds(
    lambda auto, prune, heal, options: SyncSettings(
        auto, auto and prune, auto and heal, tuple(dict.fromkeys(options))
    ),
    st.booleans(),
    st.booleans(),
    st.booleans(),
    st.lists(st.sampled_from(KNOWN_SYNC_OPTIONS), max_size=3),
)
_policies = st.one_of(
    st.none(),
    _settings.map(lambda s: {"syncPolicy": full_policy(s)}),
)


@given(_policies, _settings)
def test_an_override_on_any_team_default_gives_exactly_the_settings(
    team: dict[str, object] | None, desired: SyncSettings
) -> None:
    layers = [team or {}]
    override = policy_override(layers, desired)
    assert sync_settings(effective_policy([*layers, {"syncPolicy": override}])) == desired


@pytest.mark.parametrize(
    ("settings", "rule"),
    [
        (SyncSettings(prune=True), "sync-without-auto"),
        (SyncSettings(self_heal=True), "sync-without-auto"),
        (SyncSettings(sync_options=("CreateNamespace",)), "sync-option-invalid"),
        (SyncSettings(sync_options=("a b=c",)), "sync-option-invalid"),
        (SyncSettings(sync_options=("A=b", "A=b")), "sync-option-invalid"),
    ],
)
def test_settings_that_argo_would_not_read_are_refused(settings: SyncSettings, rule: str) -> None:
    with pytest.raises(ChangeRefusedError) as raised:
        settings.checked()
    assert raised.value.details["rule"] == rule


def test_known_options_and_the_platform_default_are_valid() -> None:
    assert SyncSettings(True, True, True, KNOWN_SYNC_OPTIONS).checked()
    assert PLATFORM_DEFAULT.checked() == MANUAL
