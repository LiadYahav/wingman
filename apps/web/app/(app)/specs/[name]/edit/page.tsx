"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { ArrowLeft, Eye } from "lucide-react";
import { toast } from "sonner";
import jsYaml from "js-yaml";
import { api } from "@/lib/api-client";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ReviewDialog } from "@/components/common/review-dialog";
import { computeLineDiff } from "@/lib/diff";
import type { ClusterSpec, MRDetail } from "@/types";

export default function EditSpecPage() {
  const params = useParams();
  const specName = params.name as string;
  const router = useRouter();
  const [yaml, setYaml] = useState<string | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);

  const { data: spec, isLoading } = useQuery<ClusterSpec>({
    queryKey: ["specs", specName],
    queryFn: () => api.get<ClusterSpec>(`/api/day1/specs/${specName}`),
    staleTime: 60_000,
  });

  // Compute original YAML from spec (memoized, stable reference)
  const originalYaml = useMemo(() => {
    if (!spec) return "";
    return jsYaml.dump(spec, { lineWidth: 120, quotingType: '"' });
  }, [spec]);

  // Initialize yaml state when spec loads
  const effectiveYaml = yaml ?? originalYaml;

  const updateMutation = useMutation({
    mutationFn: async () => {
      let parsed: unknown;
      try {
        parsed = jsYaml.load(effectiveYaml);
      } catch (e) {
        throw new Error(`Invalid YAML: ${(e as Error).message}`);
      }
      return api.put<MRDetail>(`/api/day1/specs/${specName}`, parsed);
    },
    onSuccess: (mr) => {
      toast.success(`Update MR #${mr.iid} created: ${mr.title}`);
      setReviewOpen(false);
      router.push(`/specs/${specName}`);
    },
    onError: (err: Error) => {
      toast.error(`Failed: ${err.message}`);
      setReviewOpen(false);
    },
  });

  const handleReview = () => {
    try {
      jsYaml.load(effectiveYaml);
    } catch (e) {
      toast.error(`Invalid YAML: ${(e as Error).message}`);
      return;
    }
    setReviewOpen(true);
  };

  // Compute diff only when needed (memoized)
  const diff = useMemo(
    () => computeLineDiff(originalYaml, effectiveYaml),
    [originalYaml, effectiveYaml]
  );

  return (
    <div className="p-6 lg:p-8 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link href={`/specs/${specName}`} className={buttonVariants({ variant: "ghost", size: "icon" })}>
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >
            Edit Spec
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Editing <span className="font-medium">{specName}</span> — Review changes before submitting
          </p>
        </div>
      </div>

      <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/20">
          <span className="text-sm font-medium">{specName}.yaml</span>
          <span className="text-xs text-muted-foreground">Edit the YAML below</span>
        </div>
        {isLoading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-4 w-full" />)}
          </div>
        ) : (
          <textarea
            className="w-full font-mono text-xs bg-zinc-950 text-zinc-200 p-4 min-h-[500px] focus:outline-none resize-y leading-5"
            value={effectiveYaml}
            onChange={(e) => setYaml(e.target.value)}
            spellCheck={false}
          />
        )}
      </div>

      <div className="flex gap-3">
        <Link href={`/specs/${specName}`} className={buttonVariants({ variant: "outline" })}>
          Cancel
        </Link>
        <button
          onClick={handleReview}
          disabled={isLoading}
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors disabled:opacity-60"
        >
          <Eye className="h-4 w-4" />
          Review & Update
        </button>
      </div>

      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        title={`Review: Update Spec "${specName}"`}
        description={
          diff
            ? "Changed lines are highlighted below. Green = added, red = removed."
            : "No changes detected — the YAML is identical to the current version."
        }
        diff={diff || undefined}
        onConfirm={() => updateMutation.mutate()}
        isPending={updateMutation.isPending}
        confirmLabel="Confirm — Update Spec MR"
      >
        {!diff && (
          <p className="text-sm text-muted-foreground italic text-center py-4">
            Nothing changed.
          </p>
        )}
      </ReviewDialog>
    </div>
  );
}
