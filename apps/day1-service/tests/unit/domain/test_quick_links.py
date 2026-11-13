"""Quick Links' cards: the generated ones and the links file (ADR-0052)."""

from __future__ import annotations

from pathlib import Path

import pytest

from wingman_day1.domain.quick_links import (
    ARGOCD_LABEL,
    CONSOLE_LABEL,
    DEFAULT_ARGOCD_TEMPLATE,
    DEFAULT_COLUMNS,
    NO_DOMAIN,
    NO_HUB_DOMAIN,
    ClusterOverride,
    GeneratedLinks,
    LinksFileState,
    MceInfo,
    UrlTemplates,
    generated_sections,
    is_http_url,
    parse_links_file,
    render,
    slug,
    template_problems,
    unreadable_links_file,
)

ROOT = Path(__file__).resolve().parents[5]
DEMO = ROOT / "dev/fleet-fixtures/quick-links-links.yaml"
MCES = [
    MceInfo("site2", "ocp4-prod-mce-site2-a", "4.16.27-x86_64", 1),
    MceInfo("site1", "ocp4-prod-mce-site1-a", "4.18.22-x86_64", 3),
    MceInfo("site1", "ocp4-prep-mce-site1-a", None, 0),
]


def config(**changes: object) -> GeneratedLinks:
    values: dict[str, object] = {
        "hub": "hub-prod",
        "hub_domain": "example.internal",
        "domain": "example.internal",
    }
    values.update(changes)
    return GeneratedLinks(**values)  # ty: ignore[invalid-argument-type]


# ── URL templates ─────────────────────────────────────────────────────────────


def test_the_default_templates_are_the_openshift_gitops_and_console_routes() -> None:
    templates = UrlTemplates()
    assert render(templates.argocd, cluster="mce-a", domain="example.internal") == (
        "https://openshift-gitops-server-openshift-gitops.apps.mce-a.example.internal"
    )
    assert render(templates.console, cluster="mce-a", domain="example.internal") == (
        "https://console-openshift-console.apps.mce-a.example.internal"
    )
    assert template_problems(templates.argocd) == []
    assert template_problems(templates.console) == []


@pytest.mark.parametrize(
    ("template", "problem"),
    [
        ("https://argocd.apps.example.internal", "must contain {cluster}"),
        ("https://{cluster}.{region}.example.internal", "not {region}"),
        ("ftp://{cluster}.example.internal", "http(s) URL"),
        ("https://{cluster", "is not a pattern"),
    ],
)
def test_a_template_must_make_a_cluster_url(template: str, problem: str) -> None:
    assert any(problem in line for line in template_problems(template))


# ── Generated cards ───────────────────────────────────────────────────────────


def test_the_hub_comes_first_then_one_section_per_site_sorted() -> None:
    sections, problems = generated_sections(config(), MCES, {})
    assert problems == []
    assert [s.id for s in sections] == ["hub", "site:site1", "site:site2"]
    assert [s.name for s in sections] == ["Hub", "MCEs in site1", "MCEs in site2"]
    assert all(s.generated and s.columns == DEFAULT_COLUMNS for s in sections)
    assert [c.name for c in sections[1].cards] == ["ocp4-prep-mce-site1-a", "ocp4-prod-mce-site1-a"]


def test_a_cluster_card_opens_its_argocd_with_the_console_beside_it() -> None:
    sections, _ = generated_sections(config(), MCES, {})
    hub = sections[0].cards[0]
    assert hub.id == "hub:hub-prod"
    assert hub.icon == "argocd"
    assert [link.label for link in hub.links] == [ARGOCD_LABEL, CONSOLE_LABEL]
    argocd = "https://openshift-gitops-server-openshift-gitops.apps.hub-prod.example.internal"
    assert hub.links[0].url == argocd
    assert hub.links[1].url == "https://console-openshift-console.apps.hub-prod.example.internal"
    prod = sections[1].cards[1]
    assert prod.id == "cluster:ocp4-prod-mce-site1-a"
    assert prod.links[0].url == (
        "https://openshift-gitops-server-openshift-gitops.apps.ocp4-prod-mce-site1-a.example.internal"
    )


def test_an_mce_card_says_its_hub_version_and_how_many_clusters_it_holds() -> None:
    sections, _ = generated_sections(config(), MCES, {})
    prep, prod = sections[1].cards
    assert prod.description == "OpenShift 4.18.22 · 3 hosted clusters"
    assert prep.description == "no hosted clusters"
    assert sections[2].cards[0].description == "OpenShift 4.16.27 · 1 hosted cluster"
    lone, _ = generated_sections(config(hub=None), [MceInfo("s", "m")], {})
    assert lone[0].cards[0].description is None


def test_an_override_replaces_a_cluster_address_and_the_rest_follow_the_template() -> None:
    overrides = {"hub-prod": ClusterOverride(argocd="https://gitops.hub.example.internal")}
    sections, _ = generated_sections(config(), [], overrides)
    hub = sections[0].cards[0]
    assert hub.links[0].url == "https://gitops.hub.example.internal"
    assert hub.links[1].url == "https://console-openshift-console.apps.hub-prod.example.internal"


def test_no_hub_name_means_no_hub_section() -> None:
    sections, problems = generated_sections(config(hub=None), MCES, {})
    assert [s.id for s in sections] == ["site:site1", "site:site2"]
    assert problems == []


def test_without_a_domain_the_mces_are_left_out_with_one_problem() -> None:
    sections, problems = generated_sections(config(domain="", hub_domain=""), MCES, {})
    assert sections == []
    assert problems == [NO_HUB_DOMAIN, NO_DOMAIN]


def test_an_override_lists_a_cluster_without_a_domain() -> None:
    overrides = {
        "ocp4-prod-mce-site2-a": ClusterOverride(console="https://console.site2.example.internal")
    }
    sections, problems = generated_sections(config(hub=None, domain=""), MCES, overrides)
    assert [s.id for s in sections] == ["site:site2"]
    card = sections[0].cards[0]
    assert [link.label for link in card.links] == [CONSOLE_LABEL]
    assert card.icon == "openshift"
    assert problems == [NO_DOMAIN]


def test_a_template_without_the_domain_needs_none() -> None:
    templates = UrlTemplates(argocd="https://argocd-{cluster}.example.internal")
    sections, problems = generated_sections(
        config(hub=None, domain="", templates=templates), MCES[:1], {}
    )
    assert problems == []
    assert [link.url for link in sections[0].cards[0].links] == [
        "https://argocd-ocp4-prod-mce-site2-a.example.internal"
    ]


# ── The links file ────────────────────────────────────────────────────────────

GOOD = """
sections:
  - name: Core GitOps
    description: The GitOps repos
    columns: 2
    links:
      - name: GitLab GitOps Project
        url: https://gitlab.example.internal/platform/gitops
        description: Main GitOps repository
        icon: gitlab
      - name: ArgoCD Main
        url: https://argocd.example.internal/
        icon: argocd
  - name: DC Systems
    links:
      - name: NetBox
        url: https://netbox.example.internal
clusters:
  hub-prod:
    argocd: https://gitops.hub-prod.example.internal
"""


def test_a_good_file_gives_its_sections_in_order() -> None:
    links = parse_links_file(GOOD)
    assert links.state is LinksFileState.LOADED
    assert links.problems == ()
    core, dc = links.sections
    assert (core.id, core.name, core.description, core.columns, core.generated) == (
        "file:core-gitops",
        "Core GitOps",
        "The GitOps repos",
        2,
        False,
    )
    gitlab, argocd = core.cards
    assert gitlab.id == "file:core-gitops:gitlab-gitops-project"
    assert gitlab.icon == "gitlab"
    assert gitlab.description == "Main GitOps repository"
    assert len(gitlab.links) == 1
    assert gitlab.links[0].label is None
    assert gitlab.links[0].url == "https://gitlab.example.internal/platform/gitops"
    assert (argocd.icon, argocd.links[0].url) == ("argocd", "https://argocd.example.internal/")
    assert dc.columns == DEFAULT_COLUMNS
    assert dc.cards[0].icon == "link"
    assert links.clusters == {
        "hub-prod": ClusterOverride(argocd="https://gitops.hub-prod.example.internal")
    }


def test_the_demo_file_has_no_problems() -> None:
    links = parse_links_file(DEMO.read_text(encoding="utf-8"))
    assert links.state is LinksFileState.LOADED
    assert links.problems == ()
    assert [s.name for s in links.sections] == [
        "Core GitOps",
        "DevOps",
        "Internal Tools",
        "DC Systems",
    ]


@pytest.mark.parametrize("text", ["", "# only a comment\n", "null\n"])
def test_an_empty_file_is_loaded_with_nothing(text: str) -> None:
    links = parse_links_file(text)
    assert (links.state, links.sections, links.problems) == (LinksFileState.LOADED, (), ())


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("sections: [\n", "not YAML (line"),
        ("- a\n- b\n", "must be a mapping"),
    ],
)
def test_a_file_that_is_not_a_mapping_is_invalid(text: str, problem: str) -> None:
    links = parse_links_file(text)
    assert links.state is LinksFileState.INVALID
    assert links.sections == ()
    assert problem in links.problems[0]


def test_a_bad_link_is_skipped_and_named_and_the_rest_is_kept() -> None:
    links = parse_links_file(
        """
sections:
  - name: Tools
    links:
      - name: Good
        url: https://good.example.internal
      - name: Typo
        href: https://typo.example.internal
      - url: https://nameless.example.internal
      - name: Relative
        url: /relative
"""
    )
    assert [c.name for c in links.sections[0].cards] == ["Good"]
    assert links.problems == (
        'sections[0] "Tools" links[1] "Typo": unknown key \'href\' (ignored)',
        'sections[0] "Tools" links[1] "Typo": url must be an http(s) URL with a host (skipped)',
        'sections[0] "Tools" links[2]: needs a name of 1 to 80 characters (skipped)',
        'sections[0] "Tools" links[3] "Relative": url must be an http(s) URL with a host (skipped)',
    )


def test_bad_optional_fields_fall_back_and_are_named() -> None:
    links = parse_links_file(
        """
sections:
  - name: Tools
    columns: 9
    links:
      - name: A
        url: https://a.example.internal
        icon: Not An Icon
        description: 7
"""
    )
    section = links.sections[0]
    card = section.cards[0]
    assert section.columns == DEFAULT_COLUMNS
    assert card.icon == "link"
    assert card.description is None
    assert links.problems == (
        'sections[0] "Tools": columns must be 1 to 6 (using 4)',
        "sections[0] \"Tools\" links[0] \"A\": icon must be a key such as 'gitlab' (using 'link')",
        'sections[0] "Tools" links[0] "A": description must be text of at most 200 characters',
    )


def test_ping_and_argocd_are_no_longer_read_and_are_named_like_any_unknown_key() -> None:
    # 3.13.1 removed the status dots and the ArgoCD counts (ADR-0052's amendment)
    links = parse_links_file(
        """
sections:
  - name: Tools
    links:
      - {name: A, url: "https://a.example.internal", ping: false, argocd: main}
"""
    )
    card = links.sections[0].cards[0]
    assert [link.url for link in card.links] == ["https://a.example.internal"]
    assert links.problems == (
        "sections[0] \"Tools\" links[0] \"A\": unknown key 'argocd', 'ping' (ignored)",
    )


def test_a_section_without_a_name_or_links_is_skipped() -> None:
    links = parse_links_file(
        """
sections:
  - links: [{name: A, url: "https://a.example.internal"}]
  - name: Empty
  - name: Broken
    links: [{name: B, url: nope}]
  - not a mapping
"""
    )
    assert links.sections == ()
    assert links.problems == (
        "sections[0]: needs a name of 1 to 80 characters (skipped)",
        'sections[1] "Empty": has no links (skipped)',
        'sections[2] "Broken" links[0] "B": url must be an http(s) URL with a host (skipped)',
        'sections[2] "Broken": has no links (skipped)',
        "sections[3]: must be a mapping with a name and links (skipped)",
    )


def test_names_are_unique_by_their_id() -> None:
    links = parse_links_file(
        """
sections:
  - name: Tools
    links:
      - {name: A, url: "https://a.example.internal"}
      - {name: a, url: "https://b.example.internal"}
  - name: tools
    links: [{name: C, url: "https://c.example.internal"}]
"""
    )
    assert [c.name for s in links.sections for c in s.cards] == ["A"]
    assert links.problems == (
        'sections[0] "Tools" links[1] "a": a link of that name is above',
        'sections[1] "tools": a section of that name is above',
    )


def test_too_many_sections_or_links_are_cut_with_a_problem() -> None:
    many_links = "\n".join(
        f"      - {{name: L{i}, url: 'https://l{i}.example.internal'}}" for i in range(101)
    )
    sections = "\n".join(
        f"  - name: S{i}\n    links: [{{name: A, url: 'https://a.example.internal'}}]"
        for i in range(51)
    )
    links = parse_links_file(f"sections:\n  - name: Big\n    links:\n{many_links}\n{sections}\n")
    assert len(links.sections) == 50
    assert len(links.sections[0].cards) == 100
    assert "sections: at most 50; the rest are left out" in links.problems
    assert 'sections[0] "Big": at most 100 links; the rest are left out' in links.problems


def test_cluster_addresses_must_be_urls() -> None:
    links = parse_links_file(
        """
clusters:
  hub-prod: {argocd: "not a url", console: "https://c.example.internal", extra: 1}
  broken: just text
"""
    )
    assert links.clusters == {"hub-prod": ClusterOverride(console="https://c.example.internal")}
    assert links.problems == (
        "clusters.hub-prod: unknown key 'extra' (ignored)",
        "clusters.hub-prod: argocd must be an http(s) URL with a host (using the pattern)",
        "clusters.broken: must be a mapping with argocd and console URLs",
    )


def test_wrong_top_level_shapes_are_named() -> None:
    links = parse_links_file("sections: {a: 1}\nclusters: [1]\nother: 2\n")
    assert links.state is LinksFileState.LOADED
    assert links.problems == (
        "unknown key 'other' (ignored)",
        "sections: must be a list",
        "clusters: must be a mapping of cluster name to its addresses",
    )


def test_an_unreadable_file_is_invalid_with_its_reason() -> None:
    links = unreadable_links_file("Permission denied")
    assert links.state is LinksFileState.INVALID
    assert links.problems == ("the links file cannot be read: Permission denied",)


# ── Helpers ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("https://a.example.internal", True),
        ("http://a:8000/x?y=1", True),
        ("https://", False),
        ("a.example.internal", False),
        ("https://a b", False),
        ("https://" + "a" * 2048, False),
    ],
)
def test_is_http_url(value: str, ok: bool) -> None:
    assert is_http_url(value) is ok


def test_slug() -> None:
    assert slug("Core GitOps") == "core-gitops"
    assert slug("  DC / Systems!! ") == "dc-systems"
    assert slug("!!!") == ""


def test_the_default_argocd_template_is_exported_for_the_settings() -> None:
    assert DEFAULT_ARGOCD_TEMPLATE.startswith("https://openshift-gitops-server-openshift-gitops")
