import { AlertTriangle, CheckCircle, Info } from "lucide-react";

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
