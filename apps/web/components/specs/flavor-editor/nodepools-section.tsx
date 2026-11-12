"use client";

import { useState } from "react";
import { AlertTriangle, ChevronRight, Lock, Network, Plus, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import { Switch } from "@/components/ui/switch";
import { ConfigListEditor } from "@/components/machine-configs/config-list-editor";
import { NETWORK_CONFIG, defaultHardware, hardwareOptions, isNetworkEntry } from "@/lib/machine-configs";
import { cn } from "@/lib/utils";
import type { ConfigEntry, MachineConfigs, TemplateField } from "@/types";
import { fieldId, inputCls, NotEnforced, ValueField } from "./controls";
import { NodeLabelsEditor, PresetInput } from "./inputs";
import {
  CONFIGS_RULE,
  addNodepool,
  configsMode,
  hardwareOf,
  isLocked,
  nodepoolCount,
  nodepoolPath,
  nodepoolValues,
  otherPoolInputs,
  poolConfigs,
  ratioLabel,
  removeNodepool,
  ruleEntries,
  setConfigsMode,
  setLocked,
  setNodepoolValue,
  setPoolHardware,
  setPoolRatio,
  setRatioOn,
  setSizedReplicas,
  ratioSize,
  setRuleEntries,
  type ConfigsMode,
  type FlavorDraft,
} from "./model";

type Update = (change: (draft: FlavorDraft) => FlavorDraft) => void;

const names = (entries: ConfigEntry[]) => entries.map((e) => e.name).join(", ");

/** The two ways a flavor sets machine configs, as two cards to choose from. */
function ConfigsModeChoice({ mode, onChange }: { mode: ConfigsMode; onChange: (mode: ConfigsMode) => void }) {
  const choices: { value: ConfigsMode; title: string; body: string }[] = [
    {
      value: "each",
      title: "Each nodepool its own",
      body: "Set machine configs per nodepool, as presets or locked by position.",
    },
    {
      value: "rule",
      title: "The same on every nodepool",
      body: "One list for all nodepools, locked as a rule; each picks its own network hardware.",
    },
  ];
  return (
    <div role="radiogroup" aria-label="Machine configs" className="grid gap-2 sm:grid-cols-2">
      {choices.map((choice) => {
        const selected = choice.value === mode;
        return (
          <button
            key={choice.value}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(choice.value)}
            onKeyDown={(e) => {
              if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) {
                e.preventDefault();
                onChange(mode === "each" ? "rule" : "each");
              }
            }}
            className={cn(
              "flex items-start gap-3 rounded-xl border p-3.5 text-left outline-none transition-[border-color,background-color,box-shadow] duration-150 focus-visible:ring-3 focus-visible:ring-ring/40",
              selected ? "border-primary/50 bg-primary/[0.06] shadow-sm" : "border-border hover:border-foreground/20 hover:bg-muted/40"
            )}
          >
            <span
              aria-hidden
              className={cn(
                "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors",
                selected ? "border-primary bg-primary" : "border-input"
              )}
            >
              {selected && <span className="h-1.5 w-1.5 rounded-full bg-primary-foreground" />}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium">{choice.title}</span>
              <span className="mt-0.5 block text-xs text-muted-foreground">{choice.body}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** What `nodepool-defaults.yaml` gives a new nodepool, or why it gives nothing. */
function DefaultsNote({ catalog, rule, defaults }: { catalog: MachineConfigs | undefined; rule: boolean; defaults: ConfigEntry[] }) {
  if (rule) {
    return defaultHardware(catalog) ? (
      <>A new nodepool gets the rule&apos;s configs, its network hardware at generic (any hardware); change it if it needs its own.</>
    ) : (
      <>A new nodepool gets the rule&apos;s configs; choose its network hardware.</>
    );
  }
  const nd = catalog?.nodepool_defaults;
  if (!nd) return null;
  if (nd.error) return <>New nodepools start empty: {nd.path} cannot be used.</>;
  if (!nd.found || defaults.length === 0) return <>New nodepools start with no machine configs (the specs repo has no {nd.path}).</>;
  return <>A new nodepool starts with the defaults: {names(defaults)}.</>;
}

function DefaultsProblems({ catalog }: { catalog: MachineConfigs | undefined }) {
  const nd = catalog?.nodepool_defaults;
  if (!nd || (!nd.error && nd.problems.length === 0)) return null;
  return (
    <div role="status" className="flex items-start gap-2 rounded-lg border border-status-warning/30 bg-status-warning/10 px-3 py-2.5 text-xs text-status-warning-fg">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <div className="min-w-0 space-y-0.5">
        <p className="font-medium">
          {nd.error ? `${nd.path} cannot be used: ${nd.error}` : `Some nodepool defaults in ${nd.path} would not resolve:`}
        </p>
        {nd.problems.length > 0 && (
          <ul className="list-disc pl-4">
            {nd.problems.map((p) => (
              <li key={p} className="break-words">{p}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/**
 * Part 2: how many nodepools a cluster of the flavor starts with and, for
 * each, its replicas, machine configs and node labels, each a preset or
 * locked (by position, §6), or the configs locked for every nodepool as one
 * rule (§9). A new nodepool starts with the nodepool defaults (ADR-0027).
 */
export function NodepoolsSection({
  draft,
  update,
  catalog,
  catalogLoading,
  defaults,
  schema,
  problems,
  configProblems,
  notEnforced,
}: {
  draft: FlavorDraft;
  update: Update;
  catalog: MachineConfigs | undefined;
  catalogLoading: boolean;
  /** Why a saved lock is not enforced (it breaks a rule); `undefined` when it is. */
  notEnforced: (path: string) => string | undefined;
  /** Copies of the nodepool defaults (none when the file is missing or unusable). */
  defaults: ConfigEntry[];
  schema: TemplateField[];
  /** Problems shown at a field: the editor's own and day1's, deeper ones prefixed. */
  problems: (path: string, options?: { deeper?: boolean }) => string[];
  /** Day1's problems for one config list, by entry index. */
  configProblems: (path: string) => Record<number, string[]>;
}) {
  const mode = configsMode(draft);
  const rule = mode === "rule";
  const count = nodepoolCount(draft);
  const shared = rule ? ruleEntries(draft) : [];

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <ConfigsModeChoice mode={mode} onChange={(m) => update((d) => setConfigsMode(d, m, defaults, defaultHardware(catalog)))} />
        <DefaultsProblems catalog={catalog} />
      </div>

      {rule && (
        <div id={fieldId(CONFIGS_RULE)} className="scroll-mt-28 space-y-3 rounded-xl border border-primary/25 bg-primary/[0.04] p-4" data-testid="configs-rule">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <h3 className="text-sm font-semibold">Machine configs on every nodepool</h3>
              <p className="text-xs text-muted-foreground">
                Every nodepool of every cluster has exactly these, in any order. {NETWORK_CONFIG} is each nodepool&apos;s own
                network config.
              </p>
            </div>
            <Badge
              className={cn(
                "gap-1",
                notEnforced(CONFIGS_RULE) && "bg-status-warning/15 text-status-warning-fg ring-status-warning/30"
              )}
            >
              <Lock aria-hidden /> Locked as a rule{notEnforced(CONFIGS_RULE) ? ", not enforced" : ""}
            </Badge>
          </div>
          {notEnforced(CONFIGS_RULE) && (
            <div className="text-xs">
              <NotEnforced reason={notEnforced(CONFIGS_RULE)!} />
            </div>
          )}
          <ConfigListEditor
            entries={shared}
            onChange={(entries) => update((d) => setRuleEntries(d, entries))}
            catalog={catalog}
            loading={catalogLoading}
            networkHardware="per-nodepool"
            label="Machine configs on every nodepool"
            hideLabel
            testId="rule-configs"
          />
          {problems(CONFIGS_RULE).length > 0 && (
            <ul role="alert" className="space-y-0.5 text-xs text-destructive">
              {problems(CONFIGS_RULE).map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {count > 1 && <RatioChoice draft={draft} update={update} />}

      {count === 0 ? (
        <div className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
          No nodepools: each cluster adds its own.
        </div>
      ) : (
        <ol className="space-y-4" aria-label="Nodepools">
          {draft.keys.map((key, index) => (
            <NodepoolCard
              key={key}
              index={index}
              draft={draft}
              update={update}
              catalog={catalog}
              catalogLoading={catalogLoading}
              defaults={defaults}
              schema={schema}
              problems={problems}
              configProblems={configProblems}
              notEnforced={notEnforced}
              canRemove={!rule || count > 1}
            />
          ))}
        </ol>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Button type="button" variant="outline" onClick={() => update((d) => addNodepool(d, defaults, defaultHardware(catalog)))}>
          <Plus /> Add nodepool
        </Button>
        <p className="text-xs text-muted-foreground">
          <DefaultsNote catalog={catalog} rule={rule} defaults={defaults} />
        </p>
      </div>
    </div>
  );
}

/** Whether the nodepools grow together by a ratio; each card then has its part (ADR-0040). */
function RatioChoice({ draft, update }: { draft: FlavorDraft; update: Update }) {
  const on = draft.ratio.length > 0;
  const size = on ? ratioSize(draft) : null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3.5" data-testid="nodepool-ratio">
      <div className="min-w-0">
        <h3 className="text-sm font-semibold">Sized by a ratio</h3>
        <p className="text-xs text-muted-foreground">
          {on ? (
            <>
              Nodepools grow together at <span className="font-mono text-foreground" data-testid="nodepool-ratio-label">{ratioLabel(draft)}</span>
              {size !== null ? (
                <>
                  {" "}· replicas{" "}
                  <span className="font-mono text-foreground" data-testid="nodepool-ratio-replicas">
                    {draft.ratio.map((r) => Number(r) * size).join(" · ")}
                  </span>{" "}
                  = {draft.ratio.reduce((sum, r) => sum + Number(r) * size, 0)} nodes
                </>
              ) : (
                ": set any nodepool's replicas and the others follow; each cluster can resize them together."
              )}
            </>
          ) : (
            "Off: each cluster sets every nodepool's replicas. Turn on to keep them in proportion, like zones at 1:2:1."
          )}
        </p>
      </div>
      <Switch
        aria-label="Size the nodepools by a ratio"
        checked={on}
        onCheckedChange={(checked) => update((d) => setRatioOn(d, checked))}
      />
    </div>
  );
}

function NodepoolCard({
  index,
  draft,
  update,
  catalog,
  catalogLoading,
  defaults,
  schema,
  problems,
  configProblems,
  notEnforced,
  canRemove,
}: {
  index: number;
  draft: FlavorDraft;
  update: Update;
  catalog: MachineConfigs | undefined;
  catalogLoading: boolean;
  defaults: ConfigEntry[];
  schema: TemplateField[];
  problems: (path: string, options?: { deeper?: boolean }) => string[];
  configProblems: (path: string) => Record<number, string[]>;
  notEnforced: (path: string) => string | undefined;
  canRemove: boolean;
}) {
  const pool = nodepoolValues(draft, index);
  const rule = configsMode(draft) === "rule";
  const title = `Nodepool ${index + 1}`;
  const replicasPath = nodepoolPath(index, "replicas");
  const configsPath = nodepoolPath(index, "configs");
  const labelsPath = nodepoolPath(index, "node_labels");
  const entries = poolConfigs(draft, index);
  const others = otherPoolInputs(schema, pool);
  const [moreOpen, setMoreOpen] = useState(() => others.some((o) => pool[o.name] !== undefined));
  const setValue = (key: string, value: unknown) => update((d) => setNodepoolValue(d, index, key, value));
  const setLock = (path: string, locked: boolean) => update((d) => setLocked(d, path, locked));
  const replicas = pool.replicas;
  const hardware = hardwareOf(entries);
  const configsLocked = isLocked(draft, configsPath);
  const ratioPath = nodepoolPath(index, "ratio");
  const ratioProblems = problems(ratioPath);

  return (
    <li className="rounded-xl border bg-card shadow-card" data-testid={`nodepool-${index}`} aria-label={title}>
      <div className="flex items-center justify-between gap-3 border-b px-4 py-2.5">
        <h3 className="text-sm font-semibold">{title}</h3>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-muted-foreground hover:text-destructive"
          disabled={!canRemove}
          onClick={() => update((d) => removeNodepool(d, index))}
          aria-label={`Remove nodepool ${index + 1}`}
        >
          <Trash2 /> Remove
        </Button>
      </div>
      <div className="space-y-6 p-4">
        <ValueField
          path={replicasPath}
          label="Replicas"
          locked={isLocked(draft, replicasPath)}
          onLockedChange={(locked) => setLock(replicasPath, locked)}
          notEnforced={notEnforced(replicasPath)}
          empty={replicas === undefined || replicas === ""}
          problems={problems(replicasPath, { deeper: true })}
          className="max-w-[17rem]"
        >
          {({ inputId, describedBy, invalid }) => (
            <input
              id={inputId}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              className={cn(inputCls, "w-28 font-mono tabular")}
              inputMode="numeric"
              autoComplete="off"
              placeholder="Not set"
              value={replicas === undefined ? "" : String(replicas)}
              onChange={(e) => {
                const text = e.target.value.trim();
                const value = text === "" ? undefined : /^\d+$/.test(text) ? Number(text) : text;
                // Under a ratio the nodepools move together: this one's replicas set the others'
                if (draft.ratio.length > 0) update((d) => setSizedReplicas(d, index, value));
                else setValue("replicas", value);
              }}
            />
          )}
        </ValueField>

        {draft.ratio.length > 0 && (
          <div id={fieldId(ratioPath)} className="scroll-mt-28 space-y-1.5" data-testid={`nodepool-${index}-ratio`}>
            <label htmlFor={`${fieldId(ratioPath)}-input`} className="block text-sm font-medium">
              Ratio
            </label>
            <input
              id={`${fieldId(ratioPath)}-input`}
              aria-invalid={ratioProblems.length > 0}
              aria-describedby={`${fieldId(ratioPath)}-hint`}
              className={cn(inputCls, "w-28 font-mono tabular")}
              inputMode="numeric"
              autoComplete="off"
              value={draft.ratio[index] ?? ""}
              onChange={(e) => update((d) => setPoolRatio(d, index, e.target.value))}
            />
            <p id={`${fieldId(ratioPath)}-hint`} className="text-xs text-muted-foreground">
              This nodepool&apos;s part: change any nodepool&apos;s replicas and the others follow at{" "}
              <span className="font-mono">{ratioLabel(draft)}</span>. A cluster starts at these replicas and can resize
              them together.
            </p>
            {ratioProblems.length > 0 && (
              <ul role="alert" className="space-y-0.5 text-xs text-destructive">
                {ratioProblems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {rule ? (
          <ValueField
            path={configsPath}
            label="Network hardware"
            empty={!hardware}
            problems={problems(configsPath, { deeper: true })}
            hint="A preset: a cluster may choose other hardware for this nodepool."
            labelsInput={false}
          >
            {({ invalid }) => (
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <Network className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                  <Combobox
                    className="w-56"
                    options={hardwareOptions(catalog)}
                    value={hardware}
                    onValueChange={(hw) => update((d) => setPoolHardware(d, index, hw))}
                    placeholder={catalogLoading ? "Loading hardware types…" : "Choose hardware…"}
                    searchPlaceholder="Search hardware types…"
                    emptyMessage="No hardware type matches."
                    disabled={catalogLoading}
                    aria-label={`${title} network hardware`}
                    aria-invalid={invalid}
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  Gets the rule&apos;s configs:{" "}
                  <span className="font-mono text-foreground/80">
                    {entries.map((e) => (isNetworkEntry(e) ? `${NETWORK_CONFIG}${e.hardware ? ` (${e.hardware})` : ""}` : e.name)).join(", ") || "none"}
                  </span>
                </p>
              </div>
            )}
          </ValueField>
        ) : (
          <ValueField
            path={configsPath}
            label="Machine configs"
            locked={configsLocked}
            onLockedChange={(locked) => setLock(configsPath, locked)}
            notEnforced={notEnforced(configsPath)}
            empty={pool.configs === undefined}
            problems={problems(configsPath)}
            labelsInput={false}
          >
            {() => (
              <div className="space-y-2">
                <ConfigListEditor
                  entries={entries}
                  onChange={(next) => setValue("configs", next.length === 0 && !configsLocked ? undefined : next)}
                  catalog={catalog}
                  loading={catalogLoading}
                  problems={configProblems(configsPath)}
                  label={`${title} machine configs`}
                  hideLabel
                  testId={`nodepool-${index}-configs`}
                />
                {entries.length === 0 && defaults.length > 0 && (
                  <Button type="button" variant="link" size="sm" className="h-auto px-0" onClick={() => setValue("configs", defaults)}>
                    Use the defaults ({names(defaults)})
                  </Button>
                )}
              </div>
            )}
          </ValueField>
        )}

        <ValueField
          path={labelsPath}
          label="Node labels"
          locked={isLocked(draft, labelsPath)}
          onLockedChange={(locked) => setLock(labelsPath, locked)}
          notEnforced={notEnforced(labelsPath)}
          empty={pool.node_labels === undefined}
          problems={problems(labelsPath, { deeper: true })}
          labelsInput={false}
        >
          {({ inputId, describedBy, invalid }) => (
            <NodeLabelsEditor
              id={inputId}
              describedBy={describedBy}
              invalid={invalid}
              label={`${title} node labels`}
              value={pool.node_labels}
              onChange={(labels) => setValue("node_labels", labels ?? (isLocked(draft, labelsPath) ? {} : undefined))}
            />
          )}
        </ValueField>

        {others.length > 0 && (
          <div className="space-y-3">
            <button
              type="button"
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen((v) => !v)}
              className="flex items-center gap-1.5 text-[13px] font-medium"
            >
              <ChevronRight
                aria-hidden
                className={cn("h-4 w-4 text-muted-foreground transition-transform duration-200", moreOpen && "rotate-90")}
              />
              Other inputs
              <span className="font-normal text-muted-foreground">· {others.map((o) => o.name).join(", ")}, presets only</span>
            </button>
            {moreOpen && (
              <div className="grid gap-x-5 gap-y-4 pl-6 sm:grid-cols-2">
                {others.map((input) => (
                  <PresetInput
                    key={input.name}
                    input={input}
                    path={nodepoolPath(index, input.name)}
                    value={pool[input.name]}
                    onChange={(v) => setValue(input.name, v)}
                    problems={problems(nodepoolPath(index, input.name), { deeper: true })}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

