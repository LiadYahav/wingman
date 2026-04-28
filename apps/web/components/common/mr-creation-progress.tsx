"use client";

import { useState, useEffect } from "react";
import { GitBranch, GitCommit, GitPullRequest, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

const PHASES = [
  { icon: GitBranch, label: "Preparing changes" },
  { icon: GitCommit, label: "Pushing to GitLab" },
  { icon: GitPullRequest, label: "Opening merge request" },
] as const;

// Timings approximate typical GitLab API latency so phases feel meaningful
const PHASE_DELAYS_MS = [0, 700, 1500];

export function MRCreationProgress() {
  const [activePhase, setActivePhase] = useState(0);

  useEffect(() => {
    const timers = PHASE_DELAYS_MS.slice(1).map((delay, i) =>
      setTimeout(() => setActivePhase(i + 1), delay)
    );
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="py-6 flex flex-col items-center gap-5">
      <div className="space-y-2 w-full max-w-sm">
        {PHASES.map((phase, i) => {
          const done = activePhase > i;
          const active = activePhase === i;
          return (
            <div
              key={i}
              className={cn(
                "flex items-center gap-3 rounded-lg px-4 py-2.5 transition-all duration-500",
                done && "bg-[#00c875]/5",
                active && "bg-primary/5",
                !done && !active && "opacity-35",
              )}
            >
              <div
                className={cn(
                  "rounded-full p-1.5 transition-colors duration-400",
                  done ? "bg-[#00c875]/15" : active ? "bg-primary/12" : "bg-muted",
                )}
              >
                <phase.icon
                  className={cn(
                    "h-3.5 w-3.5 transition-colors duration-400",
                    done ? "text-[#00c875]" : active ? "text-primary" : "text-muted-foreground",
                  )}
                />
              </div>
              <span
                className={cn(
                  "text-sm flex-1 transition-colors duration-400",
                  done && "font-medium",
                  !done && !active && "text-muted-foreground",
                )}
              >
                {phase.label}
              </span>
              {active && (
                <span className="flex gap-1 items-center">
                  {[0, 1, 2].map((d) => (
                    <span
                      key={d}
                      className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce"
                      style={{ animationDelay: `${d * 160}ms` }}
                    />
                  ))}
                </span>
              )}
              {done && (
                <CheckCircle2 className="h-3.5 w-3.5 text-[#00c875] shrink-0 animate-in zoom-in-75 duration-200" />
              )}
            </div>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground animate-pulse">
        Creating GitLab MR — requires approval before merging
      </p>
    </div>
  );
}
