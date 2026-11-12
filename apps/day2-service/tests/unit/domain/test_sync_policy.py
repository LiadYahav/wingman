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
    automated_problem,
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


def test_argo_reads_enabled_false_as_manual_sync() -> None:
    # ArgoCD's SyncPolicy.IsAutomatedSyncEnabled: automated set and enabled absent or true.
    paused = {"automated": {"enabled": False, "prune": True, "selfHeal": True}}
    assert sync_settings(paused) == SyncSettings()
    assert sync_settings({"automated": {"enabled": True, "prune": True}}) == SyncSettings(
        True, True, False
    )
    assert sync_settings({"automated": {"enabled": None}}) == SyncSettings(auto_sync=True)
    leaf = leaf_application(
        {"repourl": "x", "syncPolicy": paused}, team="t", chart="c", ref=ClusterRef.hub()
    )
    assert not leaf.auto_sync
    assert automated_problem(paused) is None


@pytest.mark.parametrize(
    ("policy", "says"),
    [
        ({"automated": True}, "`syncPolicy.automated: true` is not a map"),
        ({"automated": False}, "`syncPolicy.automated: false` is not a map"),
        ({"automated": "yes"}, '`syncPolicy.automated: "yes"` is not a map'),
        ({"automated": {"enabled": "false"}}, '`syncPolicy.automated.enabled: "false"` is not'),
        (True, "`syncPolicy: true` is not a map"),
    ],
)
def test_an_automated_argo_cannot_take_is_manual_sync_and_a_problem(
    policy: object, says: str
) -> None:
    # The Application CRD wants a map (and a boolean enabled); ArgoCD never gets the leaf.
    assert sync_settings(policy) == SyncSettings()
    assert says in (automated_problem(policy) or "")


@pytest.mark.parametrize(
    "policy", [None, {}, False, {"automated": None}, {"automated": {}}, {"retry": {"limit": 2}}]
)
def test_policies_argo_takes_have_no_problem(policy: object) -> None:
    assert automated_problem(policy) is None


def test_a_team_default_turns_a_paused_or_unreadable_automated_into_what_was_asked() -> None:
    paused = {"automated": {"enabled": False, "allowEmpty": True, "prune": True}}
    on = full_policy(AUTO, paused)
    assert on == {"automated": {"allowEmpty": True, "prune": False, "selfHeal": True}}
    assert sync_settings(on) == AUTO
    # Manual sync keeps ArgoCD's switched-off map as it is written: that is what it is for.
    assert full_policy(SyncSettings(), paused) == paused
    assert full_policy(SyncSettings(), {"automated": True}) == {}
    assert full_policy(SyncSettings(), {"automated": {"enabled": "no"}}) == {}
    assert full_policy(AUTO, {"automated": True}) == {
        "automated": {"prune": False, "selfHeal": True}
    }


def test_a_fleet_override_switches_auto_sync_back_on_over_enabled_false() -> None:
    paused = {"syncPolicy": {"automated": {"enabled": False, "selfHeal": True}}}
    assert policy_override([paused], AUTO) == {
        "automated": {"prune": False, "selfHeal": True, "enabled": True}
    }
    assert policy_override([paused], SyncSettings()) == {}
    # A value ArgoCD refuses is replaced, so the leaf it renders is one ArgoCD takes.
    assert policy_override([{"syncPolicy": {"automated": True}}], SyncSettings()) == {
        "automated": None
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
_automated = st.one_of(
    st.none(),
    st.sampled_from([True, False, "yes"]),
    st.fixed_dictionaries(
        {},
        optional={
            "enabled": st.sampled_from([True, False, None, "false"]),
            "prune": st.booleans(),
            "selfHeal": st.booleans(),
            "allowEmpty": st.booleans(),
        },
    ),
)
_written = st.builds(
    lambda automated, options: {
        **({} if automated is ... else {"automated": automated}),
        **({"syncOptions": options} if options else {}),
    },
    st.one_of(st.just(...), _automated),
    st.lists(st.sampled_from(KNOWN_SYNC_OPTIONS), max_size=3, unique=True),
)
"""A ``syncPolicy`` as people write it, including what ArgoCD switches off or refuses."""
_policies = st.one_of(
    st.none(),
    _settings.map(lambda s: {"syncPolicy": full_policy(s)}),
    _written.map(lambda policy: {"syncPolicy": policy}),
)


@given(_policies, _settings)
def test_an_override_on_any_team_default_gives_exactly_the_settings(
    team: dict[str, object] | None, desired: SyncSettings
) -> None:
    layers = [team or {}]
    override = policy_override(layers, desired)
    effective = effective_policy([*layers, {"syncPolicy": override}])
    assert sync_settings(effective) == desired
    assert automated_problem(effective) is None


@given(_written, _settings)
def test_a_team_default_policy_gives_exactly_the_settings_over_anything_written(
    current: dict[str, object], desired: SyncSettings
) -> None:
    policy = full_policy(desired, current)
    assert sync_settings(policy) == desired
    assert automated_problem(policy) is None


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
