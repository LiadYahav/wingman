import { Check, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

/** The box of a check toggle; `mixed` for "some of these". */
function CheckMark({ checked, disabled }: { checked: boolean | "mixed"; disabled?: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors",
        checked
          ? "border-primary bg-primary text-primary-foreground"
          : "border-muted-foreground/40 bg-background group-hover/check:border-primary/60",
        disabled && "opacity-50"
      )}
    >
      {checked === "mixed" ? (
        <Minus className="h-3 w-3" strokeWidth={3} />
      ) : checked ? (
        <Check className="h-3 w-3" strokeWidth={3} />
      ) : null}
    </span>
  );
}

/**
 * A whole row that is one checkbox: the box and everything it is about, so
 * the hit area is the row and the accessible name is what the row says.
 */
export function CheckToggle({
  checked,
  onCheckedChange,
  disabled,
  className,
  children,
  ...props
}: {
  checked: boolean | "mixed";
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
  children: React.ReactNode;
  "data-testid"?: string;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked === "mixed" ? "mixed" : checked}
      aria-disabled={disabled || undefined}
      onClick={() => {
        if (!disabled) onCheckedChange(checked !== true);
      }}
      className={cn(
        "group/check flex w-full items-start gap-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
        disabled ? "cursor-not-allowed" : "cursor-pointer",
        className
      )}
      {...props}
    >
      <CheckMark checked={checked} disabled={disabled} />
      <span className="min-w-0 flex-1">{children}</span>
    </button>
  );
}
