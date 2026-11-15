"use client";

import Link from "next/link";
import { RotateCcw } from "lucide-react";
import { ApiError, errorMessages, isApiError } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { ProblemList } from "@/components/common/problem-list";
import { writeErrorTitle } from "@/lib/write-errors";

/** Why a save did not go through, at the top; a 422's problems that have a field are shown there instead. */
export function SaveProblems({
  error,
  unmatched,
  routed,
  name,
  onReload,
}: {
  error: unknown;
  unmatched: string[];
  routed: number;
  name: string;
  onReload?: () => void;
}) {
  if (isApiError(error, "REVISION_CONFLICT")) {
    return (
      <div className="space-y-2">
        <ProblemList error={error} title="This flavor changed since you opened it. Reload it and make your edits again." />
        {onReload && (
          <Button variant="outline" size="sm" onClick={onReload}>
            <RotateCcw /> Reload flavor
          </Button>
        )}
      </div>
    );
  }
  if (isApiError(error, "ALREADY_EXISTS")) {
    return (
      <div className="space-y-2">
        <ProblemList error={error} title={`A flavor named "${name}" already exists. Pick another name, or edit that flavor.`} />
        <Link href={`/specs/${encodeURIComponent(name)}`} className="text-sm text-primary hover:underline">
          Open the existing flavor
        </Link>
      </div>
    );
  }
  if (isApiError(error, "VALIDATION_ERROR")) {
    const title = (error as ApiError).message;
    const lines = [...unmatched];
    if (routed > 0) lines.push(routed === 1 ? "One more is shown at its field below." : `${routed} more are shown at their fields below.`);
    return <ProblemList error={error} lines={lines.length > 0 ? lines : errorMessages(error)} title={title} />;
  }
  return <ProblemList error={error} title={writeErrorTitle(error, "The flavor was not saved")} />;
}
