import { AlertTriangle, CheckCircle, Info, Terminal } from "lucide-react";

/** The docs page's small pieces that its sections in other files share. */

export function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-mono text-foreground break-words">{children}</code>
  );
}

export function Callout({ type, title, children }: { type: "info" | "warning" | "tip" | "danger"; title?: string; children: React.ReactNode }) {
  const map = {
    info: { bg: "bg-blue-500/5 border-blue-500/25", text: "text-blue-600 dark:text-blue-400", Icon: Info },
    tip: { bg: "bg-emerald-500/5 border-emerald-500/25", text: "text-emerald-600 dark:text-emerald-400", Icon: CheckCircle },
    warning: { bg: "bg-amber-500/5 border-amber-500/25", text: "text-amber-600 dark:text-amber-400", Icon: AlertTriangle },
    danger: { bg: "bg-red-500/5 border-red-500/25", text: "text-red-600 dark:text-red-400", Icon: AlertTriangle },
  };
  const { bg, text, Icon } = map[type];
  return (
    <div className={`rounded-xl border p-4 ${bg}`}>
      <div className={`flex items-center gap-2 mb-1.5 ${text}`}>
        <Icon className="h-4 w-4 shrink-0" />
        {title && <p className="text-sm font-semibold">{title}</p>}
      </div>
      <div className="text-sm text-muted-foreground leading-relaxed pl-6">{children}</div>
    </div>
  );
}

export function CodeBlock({ language, children }: { language?: string; children: string }) {
  return (
    <div className="rounded-xl border bg-[#0d1117] dark:bg-zinc-900 overflow-hidden text-xs">
      {language && (
        <div className="flex items-center gap-2 px-4 py-2 border-b border-white/10 bg-white/5">
          <Terminal className="h-3 w-3 text-muted-foreground" />
          <span className="text-muted-foreground font-mono text-[10px] uppercase tracking-wider">{language}</span>
        </div>
      )}
      <pre className="px-4 py-3.5 overflow-x-auto leading-relaxed">
        <code className="text-[#e6edf3] font-mono whitespace-pre">{children}</code>
      </pre>
    </div>
  );
}

export function Step({ n, title, children }: { n: number; title?: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 items-start">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-[11px] font-bold text-primary-foreground mt-0.5">
        {n}
      </div>
      <div className="flex-1 min-w-0">
        {title && <p className="text-sm font-semibold mb-0.5">{title}</p>}
        <div className="text-sm text-muted-foreground leading-relaxed">{children}</div>
      </div>
    </div>
  );
}

export function SectionHeader({ id, icon: Icon, title, subtitle, badge }: {
  id: string;
  icon: React.ElementType;
  title: string;
  subtitle?: string;
  badge?: string;
}) {
  return (
    <div id={id} className="scroll-mt-8 flex items-start gap-4 pb-4 border-b mb-6">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 border border-primary/20">
        <Icon className="h-5 w-5 text-primary" />
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <h2 className="text-xl font-bold">{title}</h2>
          {badge && (
            <span className="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold bg-muted text-muted-foreground">{badge}</span>
          )}
        </div>
        {subtitle && <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>}
      </div>
    </div>
  );
}

/** A term and what it means, in a grid of them. */
export function TermCard({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="text-sm font-semibold mb-1">{title}</p>
      <p className="text-xs text-muted-foreground leading-relaxed">{desc}</p>
    </div>
  );
}
