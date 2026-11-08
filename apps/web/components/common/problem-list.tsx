import { AlertCircle } from "lucide-react";
import { ApiError, errorMessages } from "@/lib/api-client";
import { cn } from "@/lib/utils";

/**
 * An error a form must show in full: every broken rule (`details.problems`),
 * every bad field (`details.errors`), or the problem's detail. A form's own
 * checks, made before it asks the service, pass their `lines` instead.
 */
export function ProblemList({
  error,
  lines: given,
  title,
  className,
}: {
  error?: unknown;
  /** The lines to list instead of the error's. */
  lines?: string[];
  /** Defaults to the problem's detail when there are several lines to list. */
  title?: string;
  className?: string;
}) {
  const lines = given ?? errorMessages(error);
  const heading = title ?? (error instanceof ApiError && lines.length > 1 ? error.message : undefined);
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <div
      role="alert"
      className={cn(
        "rounded-lg border border-destructive/30 bg-destructive/5 px-3.5 py-3 text-sm text-destructive",
        className
      )}
    >
      <div className="flex items-start gap-2">
        <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
        <div className="min-w-0 space-y-1">
          {heading && <p className="font-medium break-words">{heading}</p>}
          {lines.length === 1 ? (
            <p className="break-words">{lines[0]}</p>
          ) : (
            <ul className="list-disc pl-4 space-y-0.5">
              {lines.map((line, i) => (
                <li key={i} className="break-words">{line}</li>
              ))}
            </ul>
          )}
          {requestId && (
            <p className="text-xs text-destructive/70 font-mono">request {requestId}</p>
          )}
        </div>
      </div>
    </div>
  );
}
