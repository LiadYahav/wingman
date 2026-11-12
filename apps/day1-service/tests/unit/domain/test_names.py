"""Naming rules: the convention read against the site folder, and what the chart derives."""

from __future__ import annotations

import pytest

from wingman_day1.domain.names import (
    Env,
    HostedClusterNaming,
    HostedClusterRef,
    NameSuggestion,
    describe_cluster,
    describe_mce,
    dns_label_problems,
    new_cluster_problems,
    short_name_of,
    suggest_cluster_name,
)

STRIP = HostedClusterNaming("ocp4-")
SANDBOX = HostedClusterNaming("")

FIXTURE_CLUSTERS = [
    # (stem, site, env, short name, sequence)
    ("ocp4-prep-eyal-site1", "site1", Env.PREP, "eyal", None),
    ("ocp4-prep-itay-site1", "site1", Env.PREP, "itay", None),
    ("ocp4-prod-hawk-site1", "site1", Env.PROD, "hawk", None),
    ("ocp4-prod-herzi-site1", "site1", Env.PROD, "herzi", None),
    ("ocp4-prod-karniol-site1", "site1", Env.PROD, "karniol", None),
    ("ocp4-prod-owl-site1", "site1", Env.PROD, "owl", None),
    ("ocp4-prep-amit-site2-a", "site2", Env.PREP, "amit", "a"),
    ("ocp4-prep-ilay-site2-a", "site2", Env.PREP, "ilay", "a"),
    ("ocp4-prep-kite-site2", "site2", Env.PREP, "kite", None),
    ("ocp4-prep-wren-site2", "site2", Env.PREP, "wren", None),
    ("ocp4-prod-didush-site2-a", "site2", Env.PROD, "didush", "a"),
]


@pytest.mark.parametrize(("stem", "site", "env", "short", "seq"), FIXTURE_CLUSTERS)
def test_every_fixture_cluster_name_reads_against_its_site(
    stem: str, site: str, env: Env, short: str, seq: str | None
) -> None:
    naming = describe_cluster(stem, site=site)
    assert naming.follows_convention
    assert (naming.env, naming.short_name, naming.sequence) == (env, short, seq)
    assert naming.problems == ()


def test_the_upgrade_demo_is_flagged_off_convention_not_rejected() -> None:
    naming = describe_cluster("ocp4-upgrade-demo", site="site1")
    assert not naming.follows_convention
    assert naming.env is None
    assert naming.short_name is None
    assert any("does not follow" in p for p in naming.problems)


def test_a_site_with_dashes_is_matched_not_split() -> None:
    naming = describe_cluster("ocp4-test-storage-site-a-a", site="site-a")
    assert (naming.env, naming.short_name, naming.sequence) == (Env.TEST, "storage", "a")
    bat = describe_cluster("ocp4-prod-web-bat-yam", site="bat-yam")
    assert (bat.env, bat.short_name, bat.sequence) == (Env.PROD, "web", None)
    with_seq = describe_cluster("ocp4-prod-web-bat-yam-2", site="bat-yam")
    assert (with_seq.short_name, with_seq.sequence) == ("web", "2")


def test_a_name_for_another_site_does_not_follow_this_sites_convention() -> None:
    assert not describe_cluster("ocp4-prod-herzi-site1", site="site2").follows_convention
    assert not describe_cluster("ocp4-prod-herzi-site1", site="site").follows_convention


@pytest.mark.parametrize(
    "stem",
    ["OCP4-prod-x-site1", "ocp4-prod-x-site1-", "ocp4_prod_x_site1", "ocp4-prod-x.y-site1"],
)
def test_names_that_are_not_dns_labels_are_reported(stem: str) -> None:
    naming = describe_cluster(stem, site="site1")
    assert not naming.follows_convention
    assert any("lowercase letters" in p for p in naming.problems)


def test_an_unknown_env_does_not_follow_the_convention() -> None:
    assert not describe_cluster("ocp4-dev-x-site1", site="site1").follows_convention


def test_dns_label_problems_reports_length_and_characters() -> None:
    assert dns_label_problems("ok-name", what="x") == []
    long_problems = dns_label_problems("a" * 64, what="cluster name")
    assert any("longer than 63" in p for p in long_problems)
    assert len(dns_label_problems("-Bad", what="x")) == 1


@pytest.mark.parametrize(
    ("mce", "site", "env", "letter"),
    [
        ("ocp4-prod-mce-site1-a", "site1", Env.PROD, "a"),
        ("ocp4-prep-mce-site1-a", "site1", Env.PREP, "a"),
        ("ocp4-prep-mce-site2-a", "site2", Env.PREP, "a"),
        ("ocp4-test-mce-bat-yam-b", "bat-yam", Env.TEST, "b"),
    ],
)
def test_convention_mces_read_their_env_and_letter(
    mce: str, site: str, env: Env, letter: str
) -> None:
    naming = describe_mce(mce, site=site)
    assert naming.follows_convention
    assert (naming.name, naming.site, naming.env, naming.letter) == (mce, site, env, letter)


def test_the_sandbox_mce_is_off_convention() -> None:
    naming = describe_mce("ocp4-mce-workflow-test", site="site1")
    assert not naming.follows_convention
    assert naming.env is None
    assert naming.letter is None
    assert naming.problems


def test_an_mce_of_another_site_is_off_convention_for_this_one() -> None:
    assert not describe_mce("ocp4-prod-mce-site1-a", site="site2").follows_convention


def test_a_valid_new_name_has_no_problems() -> None:
    assert (
        new_cluster_problems(
            "ocp4-prod-falcon-site1", site="site1", mce="ocp4-prod-mce-site1-a", naming=STRIP
        )
        == []
    )


def test_a_new_cluster_must_have_its_mces_env() -> None:
    problems = new_cluster_problems(
        "ocp4-prep-falcon-site1", site="site1", mce="ocp4-prod-mce-site1-a", naming=STRIP
    )
    assert any("does not match MCE" in p and "'prod'" in p for p in problems)


def test_new_clusters_are_refused_under_an_off_convention_mce() -> None:
    problems = new_cluster_problems(
        "ocp4-prod-falcon-site1", site="site1", mce="ocp4-mce-workflow-test", naming=STRIP
    )
    assert any("cannot be checked" in p for p in problems)


def test_a_new_name_for_the_wrong_site_is_refused() -> None:
    problems = new_cluster_problems(
        "ocp4-prod-falcon-site2", site="site1", mce="ocp4-prod-mce-site1-a", naming=STRIP
    )
    assert any("does not follow" in p for p in problems)


def test_an_off_convention_new_name_is_refused() -> None:
    problems = new_cluster_problems(
        "ocp4-upgrade-demo2", site="site1", mce="ocp4-prod-mce-site1-a", naming=STRIP
    )
    assert problems


def test_the_control_plane_namespace_must_fit_in_63_characters_when_ocp4_is_stripped() -> None:
    # hcp-<cn>-ocp4-<cn> is 10 + 2 * len(cn); cn is "prod-<name>-site1".
    fits = "ocp4-prod-" + "a" * 15 + "-site1"
    too_long = "ocp4-prod-" + "a" * 16 + "-site1"
    mce = "ocp4-prod-mce-site1-a"
    assert new_cluster_problems(fits, site="site1", mce=mce, naming=STRIP) == []
    problems = new_cluster_problems(too_long, site="site1", mce=mce, naming=STRIP)
    assert any("control-plane namespace" in p and "limit is 63" in p for p in problems)


def test_the_sandbox_keeps_the_whole_stem_so_its_limit_is_tighter() -> None:
    name = "ocp4-prod-falconx1234-site1"  # 27: 64 with the whole stem, 54 stripped
    mce = "ocp4-prod-mce-site1-a"
    assert new_cluster_problems(name, site="site1", mce=mce, naming=STRIP) == []
    problems = new_cluster_problems(name, site="site1", mce=mce, naming=SANDBOX)
    assert any("control-plane namespace" in p for p in problems)


def test_production_strips_ocp4_from_the_file_name() -> None:
    ref = STRIP.for_file("ocp4-prod-herzi-site1")
    assert ref == HostedClusterRef("prod-herzi-site1")
    assert ref.name == "ocp4-prod-herzi-site1"
    assert ref.namespace == "hcp-prod-herzi-site1"
    assert ref.control_plane_namespace == "hcp-prod-herzi-site1-ocp4-prod-herzi-site1"


def test_the_sandbox_keeps_the_full_stem() -> None:
    ref = SANDBOX.for_file("ocp4-upgrade-demo")
    assert (ref.name, ref.namespace) == ("ocp4-ocp4-upgrade-demo", "hcp-ocp4-upgrade-demo")


def test_a_stem_without_the_prefix_is_kept_as_is_when_stripping() -> None:
    assert STRIP.for_file("upgrade-demo").cluster_name == "upgrade-demo"


def test_an_explicit_cluster_name_in_the_file_wins_in_both_modes() -> None:
    assert STRIP.for_file("ocp4-x", explicit="custom").name == "ocp4-custom"
    assert SANDBOX.for_file("ocp4-x", explicit="custom").namespace == "hcp-custom"
    assert STRIP.for_file("ocp4-x", explicit="").cluster_name == "x"


def test_the_default_naming_is_production() -> None:
    assert HostedClusterNaming().strip_prefix == "ocp4-"


# ── A new cluster's sequence, and the suggested name (ADR-0040) ─────────────

PROD_MCE = "ocp4-prod-mce-site1-a"


@pytest.mark.parametrize("seq", ["01", "1", "aa", "b2"])
def test_a_new_clusters_sequence_must_be_one_letter(seq: str) -> None:
    stem = f"ocp4-prod-rcs-site1-{seq}"
    assert new_cluster_problems(stem, site="site1", mce=PROD_MCE, naming=STRIP) == [
        f"sequence {seq!r} of cluster {stem!r} must be one letter, a to z "
        "(ocp4-prod-rcs-site1-a): a number is not the convention"
    ]


def test_an_existing_numeric_sequence_still_reads_as_the_convention() -> None:
    naming = describe_cluster("ocp4-prod-rcs-site1-01", site="site1")
    assert naming.follows_convention
    assert naming.sequence == "01"


@pytest.mark.parametrize(
    "stem", ["ocp4-prod-rcs-site1-a", "ocp4-prod-rcs-site1-z", "ocp4-prod-rcs-site1"]
)
def test_a_new_name_with_a_letter_or_no_sequence_is_accepted(stem: str) -> None:
    assert new_cluster_problems(stem, site="site1", mce=PROD_MCE, naming=STRIP) == []


def _suggest(*taken: str, flavor: str = "rcs") -> NameSuggestion:
    return suggest_cluster_name(flavor, site="site1", mce=PROD_MCE, taken=set(taken), naming=STRIP)


def test_the_suggestion_is_env_flavor_site_and_the_first_free_letter() -> None:
    first = _suggest()
    assert (first.name, first.env, first.short_name, first.sequence, first.problems) == (
        "ocp4-prod-rcs-site1-a",
        Env.PROD,
        "rcs",
        "a",
        (),
    )
    assert _suggest("ocp4-prod-rcs-site1-a").name == "ocp4-prod-rcs-site1-b"
    # A free letter between taken ones is used; the bare base name takes no letter
    gap = _suggest("ocp4-prod-rcs-site1", "ocp4-prod-rcs-site1-a", "ocp4-prod-rcs-site1-c")
    assert gap.name == "ocp4-prod-rcs-site1-b"


def test_every_letter_taken_gives_no_name_and_says_why() -> None:
    suggestion = _suggest(*(f"ocp4-prod-rcs-site1-{c}" for c in "abcdefghijklmnopqrstuvwxyz"))
    assert suggestion.name is None
    assert suggestion.problems == (
        "every name from ocp4-prod-rcs-site1-a to ocp4-prod-rcs-site1-z is taken; "
        "type another name",
    )


def test_an_off_convention_mce_gives_no_env_and_no_name() -> None:
    suggestion = suggest_cluster_name(
        "rcs", site="site1", mce="ocp4-mce-workflow-test", taken=set(), naming=STRIP
    )
    assert (suggestion.name, suggestion.env) == (None, None)
    assert "does not follow ocp4-<env>-mce-site1-<letter>" in suggestion.problems[0]


def test_a_long_flavor_name_is_cut_until_the_chart_names_fit() -> None:
    suggestion = _suggest(flavor="agent-standard")
    assert suggestion.name == "ocp4-prod-agent-standar-site1-a"
    assert suggestion.problems == ()
    assert new_cluster_problems(suggestion.name, site="site1", mce=PROD_MCE, naming=STRIP) == []
    # The sandbox keeps the whole stem, so the cut is deeper
    sandbox = suggest_cluster_name(
        "agent-standard", site="site1", mce=PROD_MCE, taken=set(), naming=SANDBOX
    )
    assert sandbox.name is not None
    assert new_cluster_problems(sandbox.name, site="site1", mce=PROD_MCE, naming=SANDBOX) == []


def test_the_short_name_is_dns_safe() -> None:
    assert short_name_of("RCS_Zones..v2") == "rcs-zones-v2"
    assert short_name_of("-edge-") == "edge"
