"use client";

import { cn } from "@/lib/utils";

interface YamlDiffViewerProps {
  diff: string;
  className?: string;
}

export function YamlDiffViewer({ diff, className }: YamlDiffViewerProps) {
  if (!diff) {
    return (
      <p className="text-sm text-muted-foreground italic py-4 text-center">
        No diff available
      </p>
    );
  }

  const lines = diff.split("\n");

  return (
    <div className={cn("overflow-auto rounded-md border bg-zinc-950 text-xs font-mono", className)}>
      <pre className="p-4 leading-5">
        {lines.map((line, i) => {
          const isAdd = line.startsWith("+") && !line.startsWith("+++");
          const isDel = line.startsWith("-") && !line.startsWith("---");
          const isHunk = line.startsWith("@@");
          const isFileHeader = line.startsWith("+++") || line.startsWith("---");

          return (
            <div
              key={i}
              className={cn(
                "px-2 -mx-2",
                isAdd && "bg-green-900/40 text-green-300",
                isDel && "bg-red-900/40 text-red-300",
                isHunk && "text-blue-400",
                isFileHeader && "text-zinc-400 font-semibold",
                !isAdd && !isDel && !isHunk && !isFileHeader && "text-zinc-300",
              )}
            >
              {line || " "}
            </div>
          );
        })}
      </pre>
    </div>
  );
}
