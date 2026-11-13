/**
 * The Server Scan area's sidebar (ADR-0048): server-scan's pages, in the
 * order of its own navigation (`frontend/src/components/AppNav.tsx`: Sites,
 * Servers, Confs, Events, Jobs, Rules & Policies, Claude, Architecture), and
 * only those Wingman has built, so no entry leads nowhere. A new page is one
 * entry in `PAGES`; a section shows once it has a page.
 */

import { areaById, type NavIcon, type NavSection } from "@/lib/areas";

interface ServerScanPage {
  /** The sidebar section it sits in; sections keep the order of their first page. */
  section: string;
  /** Unique; also its test id. */
  key: string;
  label: string;
  href: string;
  icon: NavIcon;
}

const HOME = areaById("server-scan").href;

const PAGES: ServerScanPage[] = [
  { section: "Fleet", key: "sites", label: "Sites", href: HOME, icon: "site" },
  { section: "Fleet", key: "servers", label: "Servers", href: `${HOME}/servers`, icon: "servers" },
];

/** The area's home is marked on itself only; any other page on itself and below. */
function isActive(pathname: string, href: string): boolean {
  return href === HOME ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

export function serverScanSidebar(pathname: string): NavSection[] {
  const sections: NavSection[] = [];
  for (const page of PAGES) {
    let section = sections.find((s) => s.label === page.section);
    if (!section) {
      section = { label: page.section, items: [] };
      sections.push(section);
    }
    section.items.push({
      key: page.key,
      label: page.label,
      href: page.href,
      icon: page.icon,
      active: isActive(pathname, page.href),
    });
  }
  return sections;
}
