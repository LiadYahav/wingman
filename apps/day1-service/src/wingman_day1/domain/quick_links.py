"""Quick Links: the launcher's sections and cards, and what a check found (ADR-0052).

Wingman generates a card for the hub it runs on and one for every MCE of the
day1 repo, by site: each opens the cluster's ArgoCD
(``openshift-gitops-server-openshift-gitops.apps.<cluster>.<domain>``) and
has its console beside it. The URL patterns are settings
(:class:`UrlTemplates`); a cluster whose addresses differ gets its own in the
links file's ``clusters`` map. The team's other links are the links file's
``sections`` (:func:`parse_links_file`), in the style of the team's homepage
dashboard.

Pure: the file's text comes in, the cards go out; checking a URL and reading
an ArgoCD are the ports' (:class:`LinkReading`, :class:`ArgoCdReading` are
what they answer). A bad link or section is skipped and reported, never
fatal: a launcher with one typo still launches.
"""

from __future__ import annotations

import re
import string
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Final
from urllib.parse import urlsplit

import yaml

MAX_SECTIONS: Final = 50
MAX_LINKS: Final = 100
MAX_NAME: Final = 80
MAX_DESCRIPTION: Final = 200
MAX_URL: Final = 2048
MIN_COLUMNS: Final = 1
MAX_COLUMNS: Final = 6
DEFAULT_COLUMNS: Final = 4
DEFAULT_ICON: Final = "link"
ARGOCD_ICON: Final = "argocd"
ARGOCD_LABEL: Final = "ArgoCD"
CONSOLE_LABEL: Final = "Console"

DEFAULT_ARGOCD_TEMPLATE: Final = (
    "https://openshift-gitops-server-openshift-gitops.apps.{cluster}.{domain}"
)
DEFAULT_CONSOLE_TEMPLATE: Final = "https://console-openshift-console.apps.{cluster}.{domain}"
PLACEHOLDERS: Final = frozenset({"cluster", "domain"})

_ICON_KEY: Final = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_INSTANCE_KEY: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
"""An ArgoCD instance: a key of the tokens Secret (a cluster name for the generated cards)."""
_SLUG_JUNK: Final = re.compile(r"[^a-z0-9]+")

_SECTION_KEYS: Final = frozenset({"name", "description", "columns", "links"})
_LINK_KEYS: Final = frozenset({"name", "url", "description", "icon", "ping", "argocd"})
_FILE_KEYS: Final = frozenset({"sections", "clusters"})
_CLUSTER_KEYS: Final = frozenset({"argocd", "console"})


# ── What a check and an ArgoCD read answer ────────────────────────────────────


class LinkState(StrEnum):
    """A link's status dot."""

    UP = "up"
    """It answered 2xx, 3xx, 401 or 403: something is serving there."""
    DOWN = "down"
    """Any other answer, no answer in time, or no connection."""
    UNKNOWN = "unknown"
    """It could not be told: TLS could not be verified, or the URL cannot be asked."""


UP_STATUSES: Final = frozenset({401, 403})
"""Answers that are "up" outside 2xx and 3xx: a login in front of a running service."""


def state_of(http_status: int) -> LinkState:
    """Up for 2xx, 3xx (redirects are not followed), 401 and 403; down for anything else."""
    if 200 <= http_status < 400 or http_status in UP_STATUSES:
        return LinkState.UP
    return LinkState.DOWN


@dataclass(frozen=True, slots=True)
class LinkReading:
    """What checking one URL found."""

    url: str
    state: LinkState
    reason: str
    """Short and lower-case: ``answered 200``, ``no answer within 3 s``."""
    checked_at: datetime
    http_status: int | None = None
    latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SyncCounts:
    """Applications by ``status.sync.status``."""

    synced: int = 0
    out_of_sync: int = 0
    unknown: int = 0


@dataclass(frozen=True, slots=True)
class HealthCounts:
    """Applications by ``status.health.status``."""

    healthy: int = 0
    progressing: int = 0
    degraded: int = 0
    missing: int = 0
    suspended: int = 0
    unknown: int = 0


@dataclass(frozen=True, slots=True)
class AppCounts:
    """An ArgoCD's applications, counted."""

    applications: int
    sync: SyncCounts
    health: HealthCounts


_SYNC_FIELDS: Final = {"Synced": "synced", "OutOfSync": "out_of_sync"}
_HEALTH_FIELDS: Final = {
    "Healthy": "healthy",
    "Progressing": "progressing",
    "Degraded": "degraded",
    "Missing": "missing",
    "Suspended": "suspended",
}


def count_applications(statuses: Iterable[tuple[str | None, str | None]]) -> AppCounts:
    """Count ``(sync status, health status)`` pairs; anything else is ``unknown``."""
    sync = dict.fromkeys(("synced", "out_of_sync", "unknown"), 0)
    health = dict.fromkeys(
        ("healthy", "progressing", "degraded", "missing", "suspended", "unknown"), 0
    )
    total = 0
    for sync_status, health_status in statuses:
        total += 1
        sync[_SYNC_FIELDS.get(sync_status or "", "unknown")] += 1
        health[_HEALTH_FIELDS.get(health_status or "", "unknown")] += 1
    return AppCounts(total, SyncCounts(**sync), HealthCounts(**health))


@dataclass(frozen=True, slots=True)
class ArgoCdReading:
    """What reading one ArgoCD's applications found: the counts, or why not."""

    instance: str
    checked_at: datetime
    counts: AppCounts | None = None
    error: str | None = None


# ── The cards ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CardLink:
    """One link of a card; ``ping`` is the URL whose answer is its dot (``None``: no dot)."""

    label: str | None
    url: str
    ping: str | None


@dataclass(frozen=True, slots=True)
class ArgoCdTarget:
    """An ArgoCD whose applications a card counts: the token's key and the API's base URL."""

    instance: str
    url: str


@dataclass(frozen=True, slots=True)
class Card:
    """One card: ``links[0]`` is its own link (the title opens it)."""

    id: str
    name: str
    description: str | None
    icon: str
    links: tuple[CardLink, ...]
    argocd: ArgoCdTarget | None = None
    """Set only for an ArgoCD that has a token (the service drops it otherwise)."""


@dataclass(frozen=True, slots=True)
class Section:
    """A heading and its cards."""

    id: str
    name: str
    description: str | None
    columns: int
    generated: bool
    cards: tuple[Card, ...]


def without_pings(section: Section) -> Section:
    """The section with every dot off (status checks are off)."""
    return replace(
        section,
        cards=tuple(
            replace(card, links=tuple(replace(link, ping=None) for link in card.links))
            for card in section.cards
        ),
    )


def slug(text: str) -> str:
    """``Core GitOps`` → ``core-gitops``; the stable part of an id."""
    return _SLUG_JUNK.sub("-", text.lower()).strip("-")


# ── Generated cards: the hub and every MCE ───────────────────────────────────


def template_problems(template: str) -> list[str]:
    """Why ``template`` cannot be a cluster's URL pattern; empty when it can."""
    try:
        names = {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}
    except ValueError as exc:
        return [f"{template!r} is not a pattern: {exc}"]
    problems: list[str] = []
    if "cluster" not in names:
        problems.append(f"{template!r} must contain {{cluster}}")
    if unknown := sorted(names - PLACEHOLDERS):
        problems.append(
            f"{template!r} may only use {{cluster}} and {{domain}}, not "
            + ", ".join("{" + name + "}" for name in unknown)
        )
    if not problems and not is_http_url(render(template, cluster="c", domain="example.internal")):
        problems.append(f"{template!r} must make an http(s) URL with a host")
    return problems


def render(template: str, *, cluster: str, domain: str) -> str:
    """The URL ``template`` makes for ``cluster`` in ``domain``."""
    return template.format_map({"cluster": cluster, "domain": domain})


def needs_domain(template: str) -> bool:
    """Whether ``template`` uses ``{domain}``."""
    return "{domain}" in template


@dataclass(frozen=True, slots=True)
class UrlTemplates:
    """Where a cluster's ArgoCD and console are, from its name and domain."""

    argocd: str = DEFAULT_ARGOCD_TEMPLATE
    console: str = DEFAULT_CONSOLE_TEMPLATE


@dataclass(frozen=True, slots=True)
class ClusterOverride:
    """A cluster's own addresses, for one that does not follow the templates."""

    argocd: str | None = None
    console: str | None = None


@dataclass(frozen=True, slots=True)
class GeneratedLinks:
    """What the generated cards are made from (Wingman's settings)."""

    hub: str | None
    """The hub Wingman runs on (``QUICK_LINKS_HUB_NAME``); ``None``: no hub card."""
    hub_domain: str
    domain: str
    """The MCEs' domain: ``QUICK_LINKS_DOMAIN``, else ``MCE_API_DOMAIN``."""
    templates: UrlTemplates = field(default_factory=UrlTemplates)


@dataclass(frozen=True, slots=True)
class MceInfo:
    """An MCE folder of the day1 repo, as much as a card says of it."""

    site: str
    name: str
    hub_version: str | None = None
    cluster_count: int | None = None


HUB_SECTION: Final = "hub"
NO_DOMAIN: Final = (
    "Set QUICK_LINKS_DOMAIN (or MCE_API_DOMAIN) to list each MCE's ArgoCD and console."
)
NO_HUB_DOMAIN: Final = (
    "Set QUICK_LINKS_HUB_DOMAIN (or QUICK_LINKS_DOMAIN, MCE_API_DOMAIN) to list the hub's "
    "ArgoCD and console, or give the hub its addresses in the links file's clusters map."
)


def _cluster_links(
    name: str, domain: str, templates: UrlTemplates, override: ClusterOverride | None
) -> tuple[CardLink, ...]:
    """The cluster's ArgoCD and console links, each from its override or its template."""
    links: list[CardLink] = []
    for label, template, given in (
        (ARGOCD_LABEL, templates.argocd, override.argocd if override else None),
        (CONSOLE_LABEL, templates.console, override.console if override else None),
    ):
        url = given or (
            render(template, cluster=name, domain=domain)
            if domain or not needs_domain(template)
            else None
        )
        if url is not None:
            links.append(CardLink(label, url, url))
    return tuple(links)


def _cluster_card(
    card_id: str,
    name: str,
    description: str | None,
    links: tuple[CardLink, ...],
) -> Card:
    argocd = next((link for link in links if link.label == ARGOCD_LABEL), None)
    return Card(
        id=card_id,
        name=name,
        description=description,
        icon=ARGOCD_ICON if argocd else "openshift",
        links=links,
        argocd=ArgoCdTarget(name, argocd.url) if argocd else None,
    )


def _mce_description(mce: MceInfo) -> str | None:
    parts: list[str] = []
    if mce.hub_version:
        parts.append(f"OpenShift {mce.hub_version.split('-', 1)[0]}")
    if mce.cluster_count is not None:
        count = mce.cluster_count
        parts.append(
            "no hosted clusters"
            if count == 0
            else f"{count} hosted cluster{'' if count == 1 else 's'}"
        )
    return " · ".join(parts) or None


def generated_sections(
    config: GeneratedLinks,
    mces: Sequence[MceInfo],
    overrides: Mapping[str, ClusterOverride],
) -> tuple[list[Section], list[str]]:
    """The hub's section and one per site with MCEs, and what could not be generated."""
    sections: list[Section] = []
    problems: list[str] = []
    templates = config.templates
    if config.hub:
        links = _cluster_links(config.hub, config.hub_domain, templates, overrides.get(config.hub))
        if links:
            card = _cluster_card(f"hub:{config.hub}", config.hub, None, links)
            sections.append(
                Section(
                    HUB_SECTION,
                    "Hub",
                    "The cluster Wingman runs on",
                    DEFAULT_COLUMNS,
                    generated=True,
                    cards=(card,),
                )
            )
        else:
            problems.append(NO_HUB_DOMAIN)
    by_site: dict[str, list[MceInfo]] = {}
    for mce in mces:
        by_site.setdefault(mce.site, []).append(mce)
    missing_domain = False
    for site in sorted(by_site):
        cards: list[Card] = []
        for mce in sorted(by_site[site], key=lambda m: m.name):
            links = _cluster_links(mce.name, config.domain, templates, overrides.get(mce.name))
            if not links:
                missing_domain = True
                continue
            cards.append(
                _cluster_card(f"cluster:{mce.name}", mce.name, _mce_description(mce), links)
            )
        if cards:
            sections.append(
                Section(
                    f"site:{site}",
                    f"MCEs in {site}",
                    "Each MCE's ArgoCD and console",
                    DEFAULT_COLUMNS,
                    generated=True,
                    cards=tuple(cards),
                )
            )
    if missing_domain:
        problems.append(NO_DOMAIN)
    return sections, problems


# ── The links file ────────────────────────────────────────────────────────────


class LinksFileState(StrEnum):
    """Whether the links file was read."""

    LOADED = "loaded"
    """Read; parts of it may still have been skipped (its ``problems`` say which)."""
    MISSING = "missing"
    """No file at the path: no team links, which is not an error."""
    INVALID = "invalid"
    """Unreadable, not YAML, or not a mapping: no team links."""


class LinksFileUnreadableError(Exception):
    """The links file exists but cannot be read (its message says why)."""


@dataclass(frozen=True, slots=True)
class LinksFile:
    """The links file, parsed: its sections, its cluster addresses, and its problems."""

    state: LinksFileState
    sections: tuple[Section, ...] = ()
    clusters: Mapping[str, ClusterOverride] = field(default_factory=dict)
    problems: tuple[str, ...] = ()


MISSING_LINKS_FILE: Final = LinksFile(LinksFileState.MISSING)


def unreadable_links_file(reason: str) -> LinksFile:
    """A links file that exists but could not be read."""
    return LinksFile(LinksFileState.INVALID, problems=(f"the links file cannot be read: {reason}",))


def is_http_url(value: str) -> bool:
    """An absolute ``http(s)://`` URL with a host, of at most :data:`MAX_URL` characters."""
    if len(value) > MAX_URL or any(c.isspace() for c in value):
        return False
    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.hostname)


def _text(value: object, *, limit: int) -> str | None:
    """A non-empty string of at most ``limit`` characters, stripped; ``None`` otherwise."""
    if isinstance(value, str) and value.strip() and len(value.strip()) <= limit:
        return value.strip()
    return None


class _Problems:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, where: str, message: str) -> None:
        self.lines.append(f"{where}: {message}" if where else message)

    def unknown_keys(self, where: str, raw: Mapping[object, object], known: frozenset[str]) -> None:
        unknown = sorted(str(k) for k in raw if k not in known)
        if unknown:
            self.add(where, "unknown key " + ", ".join(repr(k) for k in unknown) + " (ignored)")


def parse_links_file(text: str) -> LinksFile:
    """The links file's sections and cluster addresses; every problem is listed, none is fatal.

    Not YAML, or not a mapping: ``INVALID`` and nothing. A link without a
    name or an http(s) URL is skipped, a section without a name or links
    too; the rest is kept.
    """
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (line {mark.line + 1})" if mark is not None else ""
        return LinksFile(LinksFileState.INVALID, problems=(f"the links file is not YAML{where}",))
    if raw is None:
        return LinksFile(LinksFileState.LOADED)
    if not isinstance(raw, dict):
        return LinksFile(
            LinksFileState.INVALID,
            problems=("the links file must be a mapping with 'sections' and 'clusters'",),
        )
    problems = _Problems()
    problems.unknown_keys("", raw, _FILE_KEYS)
    sections = _sections(raw.get("sections"), problems)
    clusters = _clusters(raw.get("clusters"), problems)
    return LinksFile(LinksFileState.LOADED, tuple(sections), clusters, tuple(problems.lines))


def _sections(raw: object, problems: _Problems) -> list[Section]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        problems.add("sections", "must be a list")
        return []
    if len(raw) > MAX_SECTIONS:
        problems.add("sections", f"at most {MAX_SECTIONS}; the rest are left out")
    sections: list[Section] = []
    ids: set[str] = set()
    for index, item in enumerate(raw[:MAX_SECTIONS]):
        section = _section(index, item, problems)
        if section is None:
            continue
        if section.id in ids:
            problems.add(f'sections[{index}] "{section.name}"', "a section of that name is above")
            continue
        ids.add(section.id)
        sections.append(section)
    return sections


def _section(index: int, raw: object, problems: _Problems) -> Section | None:
    where = f"sections[{index}]"
    if not isinstance(raw, dict):
        problems.add(where, "must be a mapping with a name and links (skipped)")
        return None
    name = _text(raw.get("name"), limit=MAX_NAME)
    if name is None:
        problems.add(where, f"needs a name of 1 to {MAX_NAME} characters (skipped)")
        return None
    where = f'{where} "{name}"'
    problems.unknown_keys(where, raw, _SECTION_KEYS)
    description = _description(raw.get("description"), where, problems)
    columns = raw.get("columns", DEFAULT_COLUMNS)
    if (
        isinstance(columns, bool)
        or not isinstance(columns, int)
        or not (MIN_COLUMNS <= columns <= MAX_COLUMNS)
    ):
        problems.add(
            where, f"columns must be {MIN_COLUMNS} to {MAX_COLUMNS} (using {DEFAULT_COLUMNS})"
        )
        columns = DEFAULT_COLUMNS
    section_slug = slug(name) or f"section-{index}"
    cards = _cards(raw.get("links"), where, section_slug, problems)
    if not cards:
        problems.add(where, "has no links (skipped)")
        return None
    return Section(
        f"file:{section_slug}", name, description, columns, generated=False, cards=tuple(cards)
    )


def _description(raw: object, where: str, problems: _Problems) -> str | None:
    if raw is None:
        return None
    description = _text(raw, limit=MAX_DESCRIPTION)
    if description is None:
        problems.add(where, f"description must be text of at most {MAX_DESCRIPTION} characters")
    return description


def _cards(raw: object, where: str, section_slug: str, problems: _Problems) -> list[Card]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        problems.add(where, "links must be a list")
        return []
    if len(raw) > MAX_LINKS:
        problems.add(where, f"at most {MAX_LINKS} links; the rest are left out")
    cards: list[Card] = []
    ids: set[str] = set()
    for index, item in enumerate(raw[:MAX_LINKS]):
        card = _card(f"{where} links[{index}]", item, section_slug, index, problems)
        if card is None:
            continue
        if card.id in ids:
            problems.add(f'{where} links[{index}] "{card.name}"', "a link of that name is above")
            continue
        ids.add(card.id)
        cards.append(card)
    return cards


def _card(
    where: str, raw: object, section_slug: str, index: int, problems: _Problems
) -> Card | None:
    if not isinstance(raw, dict):
        problems.add(where, "must be a mapping with a name and a url (skipped)")
        return None
    name = _text(raw.get("name"), limit=MAX_NAME)
    if name is None:
        problems.add(where, f"needs a name of 1 to {MAX_NAME} characters (skipped)")
        return None
    where = f'{where} "{name}"'
    problems.unknown_keys(where, raw, _LINK_KEYS)
    url = raw.get("url")
    if not isinstance(url, str) or not is_http_url(url.strip()):
        problems.add(where, "url must be an http(s) URL with a host (skipped)")
        return None
    url = url.strip()
    icon = raw.get("icon", DEFAULT_ICON)
    if not isinstance(icon, str) or not _ICON_KEY.match(icon):
        problems.add(where, f"icon must be a key such as 'gitlab' (using {DEFAULT_ICON!r})")
        icon = DEFAULT_ICON
    argocd: ArgoCdTarget | None = None
    instance = raw.get("argocd")
    if instance is not None:
        if isinstance(instance, str) and _INSTANCE_KEY.match(instance):
            argocd = ArgoCdTarget(instance, url)
        else:
            problems.add(where, "argocd must name a key of the ArgoCD tokens (ignored)")
    return Card(
        id=f"file:{section_slug}:{slug(name) or f'link-{index}'}",
        name=name,
        description=_description(raw.get("description"), where, problems),
        icon=icon,
        links=(CardLink(None, url, _ping(raw.get("ping", True), url, where, problems)),),
        argocd=argocd,
    )


def _ping(raw: object, url: str, where: str, problems: _Problems) -> str | None:
    """``ping``: a URL to check, ``true`` (the link's own), or ``false`` (no dot)."""
    if raw is True:
        return url
    if raw is False:
        return None
    if isinstance(raw, str) and is_http_url(raw.strip()):
        return raw.strip()
    problems.add(where, "ping must be an http(s) URL, true or false (checking the url)")
    return url


def _clusters(raw: object, problems: _Problems) -> dict[str, ClusterOverride]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        problems.add("clusters", "must be a mapping of cluster name to its addresses")
        return {}
    clusters: dict[str, ClusterOverride] = {}
    for name, addresses in raw.items():
        where = f"clusters.{name}"
        if not isinstance(name, str) or not name.strip():
            problems.add("clusters", "every key must be a cluster name")
            continue
        if not isinstance(addresses, dict):
            problems.add(where, "must be a mapping with argocd and console URLs")
            continue
        problems.unknown_keys(where, addresses, _CLUSTER_KEYS)
        urls: dict[str, str | None] = {}
        for key in sorted(_CLUSTER_KEYS):
            value = addresses.get(key)
            if value is None:
                urls[key] = None
            elif isinstance(value, str) and is_http_url(value.strip()):
                urls[key] = value.strip()
            else:
                problems.add(where, f"{key} must be an http(s) URL with a host (using the pattern)")
                urls[key] = None
        clusters[name.strip()] = ClusterOverride(argocd=urls["argocd"], console=urls["console"])
    return clusters


# ── The page ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Board:
    """Everything the page shows before the status checks answer."""

    sections: tuple[Section, ...]
    problems: tuple[str, ...]
    links_file: LinksFile
    links_path: str

    def pings(self) -> list[str]:
        """Every distinct URL a dot needs, sorted."""
        return sorted(
            {link.ping for s in self.sections for c in s.cards for link in c.links if link.ping}
        )

    def argocd_targets(self) -> list[ArgoCdTarget]:
        """Every ArgoCD a card counts, once per instance (the first card's URL wins)."""
        seen: dict[str, ArgoCdTarget] = {}
        for section in self.sections:
            for card in section.cards:
                if card.argocd is not None:
                    seen.setdefault(card.argocd.instance, card.argocd)
        return [seen[instance] for instance in sorted(seen)]


@dataclass(frozen=True, slots=True)
class StatusBoard:
    """The dots and the ArgoCD counts."""

    checks: tuple[LinkReading, ...]
    argocd: tuple[ArgoCdReading, ...]
