"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, FilePlus } from "lucide-react";
import { cn } from "@/lib/utils";

export interface GitLabFile {
  path: string;
  content?: string;
}

export interface GitLabFileGroup {
  label: string;
  files: GitLabFile[];
}

function FileRow({ file }: { file: GitLabFile }) {
  const [open, setOpen] = useState(false);
  const hasContent = Boolean(file.content);

  return (
    <div className="rounded-xl border bg-card overflow-hidden">
      <button
        className={cn(
          "flex items-center gap-2 w-full px-4 py-3 text-left transition-colors",
          hasContent && "hover:bg-primary/[0.02]",
          !hasContent && "cursor-default"
        )}
        onClick={() => hasContent && setOpen((v) => !v)}
      >
        <FilePlus className="h-3.5 w-3.5 text-[#00c875] shrink-0" />
        <span className="flex-1 text-sm font-mono font-medium break-all min-w-0">{file.path}</span>
        <span className="rounded-full px-2 py-0.5 text-xs font-medium bg-[#00c875]/10 text-[#007038] dark:text-[#00c875] shrink-0">
          new
        </span>
        {hasContent && (
          open
            ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        )}
      </button>

      {open && file.content && (
        <div className="border-t">
          <pre className="p-4 bg-zinc-950 text-zinc-200 text-xs font-mono overflow-x-auto max-h-72 overflow-y-auto leading-5 whitespace-pre">
            {file.content}
          </pre>
        </div>
      )}
    </div>
  );
}

export function GitLabFileList({ groups }: { groups: GitLabFileGroup[] }) {
  return (
    <div className="border-t pt-3 space-y-4">
      <p className="text-xs font-sans font-semibold text-muted-foreground uppercase tracking-wide">
        Files Created in GitLab
      </p>
      {groups.map((group) => (
        <div key={group.label} className="space-y-2">
          <p className="text-xs font-sans font-medium text-muted-foreground">{group.label}</p>
          <div className="space-y-2">
            {group.files.map((file) => (
              <FileRow key={file.path} file={file} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
