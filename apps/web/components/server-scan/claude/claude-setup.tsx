"use client";

import { ExternalLink } from "lucide-react";
import { CopyButton, copyValue } from "@/components/data-table/copy-cell";
import { extractPrompts } from "@/lib/server-scan/skill-text";
import { TOKEN_PLACEHOLDER, mcpCommand, skillFolder, tokenPage, unzipCommand } from "@/lib/server-scan/skill-setup";
import type { SkillAnswer } from "@/types/server-scan-skill";

const MONO = "font-mono text-[0.8rem] text-foreground";

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-4">
      <span aria-hidden className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
        {n}
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="text-sm font-semibold">{title}</h3>
        <div className="mt-1 text-sm leading-relaxed text-muted-foreground">{children}</div>
      </div>
    </li>
  );
}

/** A command on one line, scrolled sideways when long, with its copy button. */
function CommandLine({ command, label, testId }: { command: string; label: string; testId?: string }) {
  return (
    <div className="mt-2 flex items-center gap-2 rounded-lg border bg-muted/40 py-1.5 pr-1.5 pl-3">
      <code className={`min-w-0 flex-1 overflow-x-auto whitespace-nowrap ${MONO}`} data-testid={testId}>
        {command}
      </code>
      <CopyButton value={command} label={label} />
    </div>
  );
}

/** One of the skill's own example questions; a click copies it. */
function PromptChip({ prompt }: { prompt: string }) {
  return (
    <button
      type="button"
      onClick={() => void copyValue(prompt, "Prompt")}
      className="shrink-0 whitespace-nowrap rounded-full border bg-card px-3 py-1 text-left text-[0.8rem] text-muted-foreground outline-none transition-colors hover:border-foreground/30 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
    >
      “{prompt}”
    </button>
  );
}

/** server-scan's own Claude page, where its signed-in users make their token; a new tab. */
function TokenPageLink({ url, testId }: { url: string; testId: string }) {
  return (
    <a
      href={tokenPage(url)}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 font-medium text-foreground underline underline-offset-4 hover:text-primary"
      data-testid={testId}
    >
      server-scan&apos;s Claude page
      <ExternalLink aria-hidden className="h-3.5 w-3.5" />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}

/** server-scan's four steps, its words; the token is made on server-scan's own page, not here. */
export function SetupSteps({ skill }: { skill: SkillAnswer }) {
  const prompts = extractPrompts(skill.description, skill.when_to_use);
  return (
    <section aria-labelledby="skill-install" className="rounded-xl border bg-card p-6">
      <h2 id="skill-install" className="text-lg font-semibold tracking-tight">
        Set it up in a minute
      </h2>
      <ol className="mt-5 space-y-5">
        <Step n={1} title="Download the zip">
          server-scan&apos;s address (<span className={MONO}>{skill.server_scan_url}</span>) is already written into it.
        </Step>
        <Step n={2} title="Unzip it into your skills folder">
          <CommandLine command={unzipCommand(skill.name)} label="unzip command" testId="ss-unzip-command" />
        </Step>
        <Step n={3} title="Add your token">
          Create it on <TokenPageLink url={skill.server_scan_url} testId="ss-token-link" />, then open{" "}
          <span className={MONO}>{skillFolder(skill.name)}/SKILL.md</span> and replace the{" "}
          <span className={MONO} data-testid="ss-token-line">{skill.token_line}</span> placeholder. Keep it out of git.
          <p className="mt-1.5 text-xs" data-testid="ss-token-note">
            server-scan makes a personal token only for someone signed in to server-scan itself, so Wingman cannot make yours.
          </p>
        </Step>
        <Step n={4} title="Ask">
          Start Claude Code and just ask.
          {prompts.length > 0 && (
            <div className="mt-3 flex gap-2 overflow-x-auto pb-1" data-testid="ss-prompts">
              {prompts.map((prompt) => <PromptChip key={prompt} prompt={prompt} />)}
            </div>
          )}
        </Step>
      </ol>
    </section>
  );
}

/** The one command that connects Claude Code to server-scan's MCP endpoint, the token left to paste. */
export function McpSection({ serverScanUrl }: { serverScanUrl: string }) {
  return (
    <section aria-labelledby="skill-mcp">
      <h2 id="skill-mcp" className="text-lg font-semibold tracking-tight">
        Or connect it as an MCP server
      </h2>
      <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted-foreground">
        One command, nothing to unzip and no file to edit. Claude gets read-only tools to list and find servers, summarise
        the fleet, read a server&rsquo;s health and, with the auditor role, its events. It uses your token, so it sees only
        what you may.
      </p>
      <CommandLine command={mcpCommand(serverScanUrl)} label="MCP command" testId="ss-mcp-command" />
      <p className="mt-2 text-xs text-muted-foreground">
        Paste your token from <TokenPageLink url={serverScanUrl} testId="ss-mcp-token-link" /> over <span className="font-mono">{TOKEN_PLACEHOLDER}</span>.
      </p>
    </section>
  );
}
