"use client";

import { useState } from "react";
import { CopyButton } from "@/components/data-table/copy-cell";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { outline, type Heading } from "@/lib/server-scan/skill-text";
import { cn } from "@/lib/utils";
import type { SkillFile } from "@/types/server-scan-skill";

const lineId = (line: number) => `skill-line-${line}`;

/** Scroll the source to a heading's line; at once when the person asks for less motion. */
function jump(line: number) {
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.getElementById(lineId(line))?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
}

/** The file's `##` and `###` headings; each scrolls the source to its line. Wide screens only, as server-scan's. */
function Outline({ headings }: { headings: Heading[] }) {
  return (
    <nav aria-label="On this page" className="hidden border-r p-4 lg:block">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">On this page</p>
      <ul className="max-h-[70vh] space-y-0.5 overflow-y-auto">
        {headings.map((h) => (
          <li key={h.line}>
            <button
              type="button"
              onClick={() => jump(h.line)}
              className={cn(
                "w-full rounded-md px-2 py-1 text-left text-[0.8rem] text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50",
                h.level === 3 && "pl-5"
              )}
            >
              {h.text}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** The file as Claude reads it: numbered lines, headings in bold, the whole file copied in one click. */
function Lines({ file }: { file: SkillFile }) {
  const lines = file.content.split("\n");
  return (
    <div className="min-w-0">
      <div className="flex items-center justify-between border-b px-4 py-2">
        <span className="font-mono text-xs text-muted-foreground" data-testid="ss-skill-lines">
          {lines.length} lines
        </span>
        <CopyButton value={file.content} label={file.path} />
      </div>
      <pre
        tabIndex={0}
        aria-label={file.path}
        className="max-h-[70vh] overflow-auto py-3 font-mono text-[0.78rem] leading-6 outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        {lines.map((line, index) => (
          // A file's lines never reorder while it is shown, so the index is the stable key
          <div key={index} id={lineId(index)} className="flex">
            <span aria-hidden className="w-12 shrink-0 select-none pr-4 text-right text-muted-foreground/70">
              {index + 1}
            </span>
            <code className={cn("whitespace-pre-wrap break-words pr-4", line.startsWith("#") ? "font-semibold text-foreground" : "text-muted-foreground")}>
              {line || " "}
            </code>
          </div>
        ))}
      </pre>
    </div>
  );
}

/** server-scan's "What's inside": each file of the skill as a tab, its outline beside it. */
export function SkillSource({ files }: { files: SkillFile[] }) {
  const [path, setPath] = useState(files[0]?.path ?? "");
  const file = files.find((f) => f.path === path) ?? files[0];
  if (!file) return null;
  return (
    <section aria-labelledby="skill-source" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="skill-source" className="text-lg font-semibold tracking-tight">
            What&rsquo;s inside
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">Exactly what Claude reads, as server-scan serves it now.</p>
        </div>
        <Tabs value={file.path} onValueChange={(value) => setPath(String(value))}>
          <TabsList aria-label="Skill file">
            {files.map((f) => (
              <TabsTrigger key={f.path} value={f.path} className="font-mono text-xs">
                {f.path}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      <div className="grid overflow-hidden rounded-xl border bg-card lg:grid-cols-[14rem_1fr]">
        <Outline headings={outline(file.content)} />
        <Lines key={file.path} file={file} />
      </div>
    </section>
  );
}
