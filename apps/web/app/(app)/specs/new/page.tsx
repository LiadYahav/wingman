"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, Eye } from "lucide-react";
import { toast } from "sonner";
import jsYaml from "js-yaml";
import { api } from "@/lib/api-client";
import { buttonVariants } from "@/components/ui/button";
import { ReviewDialog } from "@/components/common/review-dialog";
import { asNewFile } from "@/lib/diff";
import { useIsAdmin } from "@/stores/auth-store";
import type { MRDetail } from "@/types";

const TEMPLATE = `apiVersion: wingman.io/v1
kind: ClusterSpec
metadata:
  name: my-spec
  description: "Describe your cluster spec"
  version: "1.0.0"
  labels:
    tier: production
spec:
  day1:
    variables:
      - name: cluster_name
        type: string
        required: true
        description: "Name of the cluster"
      - name: ocp_version
        type: string
        required: true
        enum:
          - "4.14.12"
          - "4.15.3"
          - "4.16.0"
    template: |
      ---
      apiVersion: hypershift.openshift.io/v1beta1
      kind: HostedCluster
      metadata:
        name: {{ cluster_name }}
      spec:
        release:
          image: registry.internal/ocp-release:{{ ocp_version }}
  day2:
    addons: []
`;

export default function NewSpecPage() {
  const isAdmin = useIsAdmin();
  const router = useRouter();
  const [yaml, setYaml] = useState(TEMPLATE);
  const [reviewOpen, setReviewOpen] = useState(false);

  const createMutation = useMutation({
    mutationFn: async () => {
      let parsed: unknown;
      try {
        parsed = jsYaml.load(yaml);
      } catch (e) {
        throw new Error(`Invalid YAML: ${(e as Error).message}`);
      }
      return api.post<MRDetail>("/api/day1/specs", parsed);
    },
    onSuccess: (mr) => {
      toast.success(`Spec MR #${mr.iid} created: ${mr.title}`);
      setReviewOpen(false);
      router.push("/specs");
    },
    onError: (err: Error) => {
      toast.error(`Failed: ${err.message}`);
      setReviewOpen(false);
    },
  });

  const handleReview = () => {
    // Validate YAML before opening review
    try {
      jsYaml.load(yaml);
    } catch (e) {
      toast.error(`Invalid YAML: ${(e as Error).message}`);
      return;
    }
    setReviewOpen(true);
  };

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-3 text-center">
        <p className="text-lg font-semibold">Insufficient permissions</p>
        <p className="text-sm text-muted-foreground">Your role (viewer) does not have access to create specs.</p>
        <Link href="/specs" className={buttonVariants({ variant: "outline", size: "sm" })}>Back to specs</Link>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/specs" className={buttonVariants({ variant: "ghost", size: "icon" })}>
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >
            New Spec
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">Define a cluster template in YAML</p>
        </div>
      </div>

      <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/20">
          <span className="text-sm font-medium">spec.yaml</span>
          <span className="text-xs text-muted-foreground">Edit the YAML — Review before submitting</span>
        </div>
        <textarea
          className="w-full font-mono text-xs bg-zinc-950 text-zinc-200 p-4 min-h-[500px] focus:outline-none resize-y leading-5"
          value={yaml}
          onChange={(e) => setYaml(e.target.value)}
          spellCheck={false}
        />
      </div>

      <div className="flex gap-3">
        <Link href="/specs" className={buttonVariants({ variant: "outline" })}>
          Cancel
        </Link>
        <button
          onClick={handleReview}
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors"
        >
          <Eye className="h-4 w-4" />
          Review & Create
        </button>
      </div>

      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        title="Review: Create Spec"
        description="The spec below will be created as a new file in GitLab and submitted as an MR for approval."
        diff={asNewFile(yaml)}
        onConfirm={() => createMutation.mutate()}
        isPending={createMutation.isPending}
        confirmLabel="Confirm — Create Spec MR"
      />
    </div>
  );
}
