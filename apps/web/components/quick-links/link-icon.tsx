import type { CSSProperties } from "react";
import {
  Activity, Bell, BookOpen, Box, Calendar, ChartLine, Cloud, Code, Compass, Cpu, Database, FileText, GitBranch, Globe,
  HardDrive, House, KeyRound, Layers, LayoutDashboard, Link2, Lock, Mail, MessageSquare, Monitor, Network, Package,
  Router, Search, Server, Settings, Shield, Terminal, Ticket, Users, Wifi, Wrench, type LucideIcon,
} from "lucide-react";
import { BRAND_ICONS, isBrandIcon } from "./brand-icons";
import { cn } from "@/lib/utils";

/**
 * The generic icons a card may name (docs/notes/2026-11-12-quick-links-api.md
 * §4), from lucide, which Wingman already ships. A static map, so the bundle
 * holds exactly these.
 */
const GENERIC_ICONS: Record<string, LucideIcon> = {
  link: Link2,
  globe: Globe,
  book: BookOpen,
  docs: FileText,
  network: Network,
  compass: Compass,
  server: Server,
  database: Database,
  storage: HardDrive,
  shield: Shield,
  lock: Lock,
  key: KeyRound,
  chart: ChartLine,
  dashboard: LayoutDashboard,
  monitor: Monitor,
  terminal: Terminal,
  code: Code,
  git: GitBranch,
  wrench: Wrench,
  settings: Settings,
  box: Box,
  package: Package,
  cloud: Cloud,
  layers: Layers,
  cpu: Cpu,
  router: Router,
  wifi: Wifi,
  mail: Mail,
  chat: MessageSquare,
  calendar: Calendar,
  users: Users,
  ticket: Ticket,
  bell: Bell,
  activity: Activity,
  search: Search,
  home: House,
};

/** Whether `key` names an icon Wingman ships; any other key shows `link`. */
const isKnownIcon = (key: string): boolean => isBrandIcon(key) || Object.hasOwn(GENERIC_ICONS, key);

/**
 * A card's icon by key, in a small rounded tile: a brand mark in its brand
 * colour (the text colour where that colour is too faint on this theme's
 * cards), or a generic lucide icon. Decorative: the card's name says what it is.
 */
export function LinkIcon({ icon, className }: { icon: string; className?: string }) {
  const known = isKnownIcon(icon) ? icon : "link";
  return (
    <span
      data-testid="quick-link-icon"
      data-icon={known}
      className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground", className)}
    >
      {isBrandIcon(known) ? <BrandMark icon={known} /> : <GenericMark icon={known} />}
    </span>
  );
}

function BrandMark({ icon }: { icon: keyof typeof BRAND_ICONS }) {
  const brand = BRAND_ICONS[icon];
  const style = {
    "--ql-light": brand.light ?? "currentColor",
    "--ql-dark": brand.dark ?? "currentColor",
  } as CSSProperties;
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden
      focusable="false"
      style={style}
      className="size-[18px] fill-[var(--ql-light)] dark:fill-[var(--ql-dark)]"
    >
      <path d={brand.path} />
    </svg>
  );
}

function GenericMark({ icon }: { icon: string }) {
  const Icon = GENERIC_ICONS[icon] ?? Link2;
  return <Icon className="size-[18px] text-muted-foreground" aria-hidden />;
}
