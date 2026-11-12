"use client";

import { useState } from "react";
import { DEFAULT_SYNC, day2Api } from "@/lib/day2";
import { parseIgnoreDifferences, type Values } from "@/lib/values";
import { buttonVariants } from "@/components/ui/button";
import { ProblemList } from "@/components/common/problem-list";
import { AuthoringReview, useAuthoringWrite } from "@/components/addons/authoring-flow";
import {
  CHART_NAME,
  IgnoreDifferencesField,
  REPO_URL,
  ScopeChoice,
  TemplateSkeleton,
  TextField,
  useAddonTemplate,
} from "@/components/addons/authoring-fields";
import { WriteError } from "@/components/addons/file-preview";
import { SyncOptionsControl } from "@/components/addons/sync-options";
import { ReadOnlyNote } from "@/components/addons/team-access";
import { YamlValuesField } from "@/components/addons/yaml-values-field";
import type { AuthoringChange, CreateAddonBody, FleetScope, SyncSettings } from "@/types/day2";

function Section({ title, description, children }: { title: string; description?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="space-y-3 rounded-xl border bg-card p-4 shadow-sm sm:p-5" aria-label={title}>
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
      </div>
      {children}
    </section>
  );
}

/**
 * A new add-on in a team's catalog (ADR-0043, ADR-0053):
 * `operators/<name>/<name>.yaml` and `values.yaml` in one MR, optionally a
 * fleet default in the same MR. It starts from the team's own files
 * (`GET /teams/{team}/addon-template`). The preview lists every cluster that
 * already has a chart of that name in its own folder and changes; they are
 * confirmed before the MR opens, against the previewed plan's digest.
 */
export function NewAddonForm({
  team,
  existing,
  readOnlyReason,
  showReason = true,
  onCancel,
  onOpened,
}: {
  team: string;
  /** The team's add-on names, which a new one cannot take. */
  existing: readonly string[];
  /** Why the team's writes are off: the form cannot be previewed. */
  readOnlyReason: string | null;
  /** Show the reason (false while the teams list loads). */
  showReason?: boolean;
  onCancel: () => void;
  onOpened: (change: AuthoringChange) => void;
}) {
  const template = useAddonTemplate(team);
  const data = template.data;
  const [name, setName] = useState("");
  const [repourl, setRepourl] = useState<string | null>(null);
  const [revision, setRevision] = useState("");
  const [path, setPath] = useState("");
  const [namespace, setNamespace] = useState<string | null>(null);
  const [sync, setSync] = useState<SyncSettings | null>(null);
  const [ignoreText, setIgnoreText] = useState("");
  const [values, setValues] = useState<Values | null>({});
  const [scope, setScope] = useState<FleetScope | null>(null);
  const [defaultValues, setDefaultValues] = useState<Values | null>({});
  const write = useAuthoringWrite<CreateAddonBody>({
    method: "post",
    url: (dryRun) => day2Api.createAddon(team, dryRun),
    onOpened,
  });

  const chart = name.trim();
  // Pre-filled while untouched: the team's usual chart-repo folder and the name as namespace.
  const repo = repourl ?? (data?.repourl_prefix && chart ? `${data.repourl_prefix}${chart}.git` : "");
  const ns = namespace ?? chart;
  const syncValue = sync ?? data?.sync ?? DEFAULT_SYNC;
  const ignore = parseIgnoreDifferences(ignoreText);

  const blocker = readOnlyReason
    ? showReason
      ? "This team is read-only in Wingman"
      : "Reading the team's write access"
    : !data
      ? "Loading the team's defaults"
      : !chart
        ? "Give the add-on a name"
        : !CHART_NAME.test(chart)
          ? "The name must be lowercase letters, digits and '-' (it becomes part of Application names)"
          : existing.includes(chart)
            ? `${team} has ${chart} already`
            : !REPO_URL.test(repo.trim())
              ? "Give the chart repo URL (http or https)"
              : !ignore.ok
                ? "Fix the ignoreDifferences YAML"
                : values === null || (scope !== null && defaultValues === null)
                  ? "Fix the values YAML"
                  : null;

  function body(): CreateAddonBody {
    const trimmedPath = path.trim();
    return {
      name: chart,
      repourl: repo.trim(),
      target_revision: revision.trim() || null,
      path: trimmedPath && trimmedPath !== "." ? trimmedPath : null,
      project_namespace: ns.trim() || null,
      sync: syncValue,
      ignore_differences: ignore.ok ? ignore.value : null,
      values: values ?? {},
      default_scope: scope,
      default_values: scope ? (defaultValues ?? {}) : {},
      confirm_changes: [],
      message: null,
    };
  }

  if (template.error && !data) {
    return <ProblemList error={template.error} title={`${team}'s defaults for a new add-on could not be loaded`} />;
  }
  if (!data) return <TemplateSkeleton />;

  return (
    <div className="space-y-5" data-testid="new-addon-form">
      {readOnlyReason && showReason && <ReadOnlyNote reason={readOnlyReason} />}
      <Section
        title="Deploy config"
        description={
          <>
            <code>operators/{chart || "<name>"}/{chart || "<name>"}.yaml</code>: where the chart comes from and how ArgoCD syncs it.
          </>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField
            label="Name"
            value={name}
            onChange={setName}
            placeholder="podinfo"
            help="The chart folder, operators/<name>/: lowercase letters, digits and '-'."
          />
          <TextField
            label="Project namespace"
            value={ns}
            onChange={setNamespace}
            placeholder="namespace"
            help="Where the chart is deployed on each cluster. Empty: none is set."
          />
        </div>
        <TextField
          label="Chart repo URL (repourl)"
          type="url"
          value={repo}
          onChange={setRepourl}
          placeholder={data.repourl_prefix ? `${data.repourl_prefix}<name>.git` : "https://gitlab.example.com/helm-charts/<name>.git"}
          help={
            <>
              Written as lowercase <code>repourl</code>, the only spelling the platform reads.
            </>
          }
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField
            label="Revision (targetRevision)"
            value={revision}
            onChange={setRevision}
            placeholder="HEAD"
            help="A branch of the chart repo. Empty: HEAD, the repo's default branch."
          />
          <TextField label="Path" value={path} onChange={setPath} placeholder="." help="The chart's folder in its repo. Empty: the root." />
        </div>
        <SyncOptionsControl value={syncValue} onChange={setSync} known={data.known_sync_options} hint={data.sync_source} />
        <IgnoreDifferencesField path={`operators/${chart || "<name>"}/${chart || "<name>"}.yaml`} text={ignoreText} onTextChange={setIgnoreText} />
      </Section>

      <Section title="Team values" description="The team default every destination starts from, above the chart's own values.">
        <YamlValuesField label="Team values" path={`operators/${chart || "<name>"}/values.yaml`} initial={{}} onChange={setValues} />
      </Section>

      <Section
        title="Fleet default"
        description="Also deploy it to every destination of one kind the team's repo has a folder for, in the same merge request. Manage it later from the add-on's page."
      >
        <ScopeChoice scopes={data.scopes} value={scope} onChange={setScope} allowNone name="Also make it a default for" />
        {scope && (
          <YamlValuesField
            label="Fleet default values"
            path={`defaults/${scope}/${chart || "<name>"}/values.yaml`}
            initial={{}}
            onChange={setDefaultValues}
            placeholder="# Empty: the team values apply on every destination."
          />
        )}
      </Section>

      <WriteError error={write.previewError} />
      <div className="flex flex-wrap items-center justify-end gap-2">
        <button type="button" onClick={onCancel} className={buttonVariants({ variant: "outline" })}>
          Cancel
        </button>
        <button
          type="button"
          onClick={() => write.preview(body())}
          disabled={Boolean(blocker) || write.previewing}
          title={blocker ?? undefined}
          className={buttonVariants()}
        >
          {write.previewing ? "Checking…" : "Preview changes"}
        </button>
      </div>
      <AuthoringReview write={write} title={`New add-on ${chart} in ${team}`} />
    </div>
  );
}
