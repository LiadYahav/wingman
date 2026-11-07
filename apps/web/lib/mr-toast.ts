import { toast } from "sonner";
import { approvalHref } from "@/lib/approvals";
import type { MRDetail } from "@/types";

/** "MR !12 opened" with a button to its review page (every change is an MR). */
export function toastMrOpened(mr: MRDetail, navigate: (href: string) => void, what = "MR"): void {
  toast.success(`${what} !${mr.iid} opened`, {
    description: mr.title,
    action: { label: "Review", onClick: () => navigate(approvalHref(mr)) },
  });
}
