"use client";

import { Loader2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { YamlDiffViewer } from "@/components/common/yaml-diff-viewer";
import { MRCreationProgress } from "@/components/common/mr-creation-progress";
import { cn } from "@/lib/utils";

interface ReviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  /** Unified diff string to render with YamlDiffViewer (green/red lines). */
  diff?: string;
  /** Arbitrary content shown below the diff (or instead of it). */
  children?: React.ReactNode;
  onConfirm: () => void;
  isPending: boolean;
  confirmLabel?: string;
  /** "default" = blue primary, "destructive" = red */
  confirmVariant?: "default" | "destructive";
  /** Additional condition to disable the confirm button (e.g., typed confirmation) */
  confirmDisabled?: boolean;
  /** Dialog size: "default" (2xl), "lg" (4xl), "xl" (5xl) */
  size?: "default" | "lg" | "xl";
  /**
   * For actions that do not open an MR (approve, reject): what is happening
   * while pending, shown instead of the MR-creation progress.
   */
  pendingLabel?: string;
}

/**
 * Shared review modal used before every mutation that creates a GitLab MR.
 * Shows what will change (diff) and requires explicit confirmation.
 */
export function ReviewDialog({
  open,
  onOpenChange,
  title,
  description,
  diff,
  children,
  onConfirm,
  isPending,
  confirmLabel = "Confirm — Create MR",
  confirmVariant = "default",
  confirmDisabled = false,
  size = "default",
  pendingLabel,
}: ReviewDialogProps) {
  const sizeClasses = {
    default: "sm:max-w-2xl",
    lg: "sm:max-w-4xl",
    xl: "sm:max-w-5xl",
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={sizeClasses[size]} showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {isPending && pendingLabel ? (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground" role="status">
            <Loader2 className="h-4 w-4 animate-spin" />
            {pendingLabel}
          </div>
        ) : isPending ? (
          <MRCreationProgress />
        ) : (
          <div className="max-h-[55vh] overflow-y-auto space-y-3 py-1">
            {diff && <YamlDiffViewer diff={diff} />}
            {children}
          </div>
        )}

        <DialogFooter>
          <button
            onClick={() => onOpenChange(false)}
            disabled={isPending}
            className={buttonVariants({ variant: "outline" })}
          >
            Back
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending || confirmDisabled}
            className={cn(
              buttonVariants({ variant: confirmVariant === "destructive" ? "destructive" : "default" })
            )}
          >
            {isPending ? pendingLabel ?? "Creating MR…" : confirmLabel}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
