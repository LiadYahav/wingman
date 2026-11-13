/**
 * Client-side line-level diff utilities.
 * Used for review dialogs to show what will change before creating an MR.
 */

import type { FileDiff } from "@/types";

type Op = { t: " " | "+" | "-"; s: string };

/** The path a file's diff is listed under: `old → new` for a rename. */
export function diffLabel(diff: FileDiff): string {
  return diff.renamed_file ? `${diff.old_path} → ${diff.new_path}` : diff.new_path || diff.old_path;
}

/** The line edit script from `A` to `B`, in order: a longest common subsequence, backtracked. */
function editScript(A: string[], B: string[]): Op[] {
  const dp = Array.from({ length: A.length + 1 }, () => new Int32Array(B.length + 1));
  for (let i = 1; i <= A.length; i++) {
    for (let j = 1; j <= B.length; j++) {
      dp[i][j] =
        A[i - 1] === B[j - 1]
          ? dp[i - 1][j - 1] + 1
          : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }

  const ops: Op[] = [];
  let i = A.length, j = B.length;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && A[i - 1] === B[j - 1]) {
      ops.unshift({ t: " ", s: A[i - 1] }); i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.unshift({ t: "+", s: B[j - 1] }); j--;
    } else {
      ops.unshift({ t: "-", s: A[i - 1] }); i--;
    }
  }
  return ops;
}

/** Compute a unified-style diff between two texts using LCS. */
export function computeLineDiff(oldText: string, newText: string): string {
  if (oldText === newText) return "";

  const A = oldText.split("\n");
  const B = newText.split("\n");

  if (A.length * B.length > 250_000) {
    return "--- before\n+++ after\n@@ file too large to diff inline @@";
  }

  const ops = editScript(A, B);

  // Mark lines to show: changed lines + 3 context lines each side
  const C = 3;
  const show = new Array(ops.length).fill(false);
  for (let k = 0; k < ops.length; k++) {
    if (ops[k].t !== " ") {
      for (let d = Math.max(0, k - C); d < Math.min(ops.length, k + C + 1); d++) {
        show[d] = true;
      }
    }
  }

  const out: string[] = ["--- before", "+++ after"];
  let inHunk = false;
  for (let k = 0; k < ops.length; k++) {
    if (show[k]) {
      if (!inHunk) { out.push("@@ ... @@"); inHunk = true; }
      out.push(`${ops[k].t}${ops[k].s}`);
    } else if (inHunk) {
      inHunk = false;
    }
  }

  return out.join("\n");
}

/**
 * Like computeLineDiff but shows the ENTIRE file — unchanged lines are
 * included as context so the user can scroll through the whole document
 * and see exactly where each change lands.
 */
export function computeFullFileDiff(oldText: string, newText: string): string {
  if (oldText === newText) return "";

  const A = oldText.split("\n");
  const B = newText.split("\n");

  if (A.length * B.length > 250_000) {
    return computeLineDiff(oldText, newText); // fall back to hunked diff for huge files
  }

  return ["--- before", "+++ after", "@@ full file @@", ...editScript(A, B).map((o) => `${o.t}${o.s}`)].join("\n");
}

/** Format entire content as a new file — all lines are additions (green). */
export function asNewFile(content: string): string {
  return [
    "--- /dev/null",
    "+++ (new file)",
    "@@ -0,0 +1 @@",
    ...content.split("\n").map((l) => `+${l}`),
  ].join("\n");
}
