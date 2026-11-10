"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { FieldGroup, inputCls, Segmented, ValueField } from "./controls";
import { PresetInput } from "./inputs";
import { isLocked, OWNERS, PLATFORM, type FlavorDraft, type OtherInput } from "./model";

const PLATFORMS = [
  { value: "", label: "Not set" },
  { value: "agent", label: "Agent" },
  { value: "kubevirt", label: "KubeVirt" },
] as const;

/**
 * Part 1: what the flavor is (name, version, description) and the values it
 * sets for the whole cluster: the owner numbers and the platform, each a
 * preset or locked, and any other template input as a preset.
 */
export function BasicsSection({
  draft,
  isNew,
  problems,
  showNameProblems,
  otherInputs,
  notEnforced,
  onName,
  onVersion,
  onDescription,
  onValue,
  onLocked,
}: {
  draft: FlavorDraft;
  isNew: boolean;
  /** Problems by field path (the editor's own and day1's). */
  problems: (path: string) => string[];
  /** Show the name and version rules only once something was typed or a save was tried. */
  showNameProblems: boolean;
  otherInputs: OtherInput[];
  /** Why a saved lock is not enforced (it breaks a rule); `undefined` when it is. */
  notEnforced: (path: string) => string | undefined;
  onName: (name: string) => void;
  onVersion: (version: string) => void;
  onDescription: (description: string) => void;
  onValue: (key: string, value: unknown) => void;
  onLocked: (path: string, locked: boolean) => void;
}) {
  const [moreOpen, setMoreOpen] = useState(() => otherInputs.some((i) => draft.values[i.name] !== undefined));
  const nameProblems = showNameProblems || draft.name ? problems("metadata.name") : [];
  const versionProblems = showNameProblems || draft.version ? problems("metadata.version") : [];
  const platform = typeof draft.values[PLATFORM] === "string" ? (draft.values[PLATFORM] as string) : "";
  const platformOptions = PLATFORMS.some((p) => p.value === platform)
    ? PLATFORMS
    : [...PLATFORMS, { value: platform, label: platform }];
  const setCount = otherInputs.filter((i) => draft.values[i.name] !== undefined).length;

  return (
    <div className="space-y-8">
      <div className="grid gap-x-5 gap-y-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,12rem)]">
        {isNew ? (
          <ValueField
            path="metadata.name"
            label="Name"
            empty={!draft.name}
            problems={nameProblems}
            hint="Lowercase letters, digits and '-'. It cannot be changed later."
          >
            {({ inputId, describedBy, invalid }) => (
              <input
                id={inputId}
                aria-describedby={describedBy}
                aria-invalid={invalid}
                data-testid="spec-name-input"
                className={inputCls}
                placeholder="e.g. agent-dell, standard-ha"
                autoComplete="off"
                spellCheck={false}
                value={draft.name}
                onChange={(e) => onName(e.target.value)}
              />
            )}
          </ValueField>
        ) : (
          <div className="min-w-0 space-y-1.5">
            <p className="flex min-h-7 items-center text-[13px] font-medium text-foreground/90">Name</p>
            <p className="flex h-9 items-center truncate font-mono text-sm" data-testid="spec-name">{draft.name}</p>
            <p className="text-xs text-muted-foreground">A flavor keeps its name.</p>
          </div>
        )}
        <ValueField path="metadata.version" label="Version" empty={!draft.version} problems={versionProblems} hint="One word, like 1.2.0.">
          {({ inputId, describedBy, invalid }) => (
            <input
              id={inputId}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              data-testid="spec-version-input"
              className={cn(inputCls, "font-mono")}
              placeholder="1.0.0"
              autoComplete="off"
              spellCheck={false}
              value={draft.version}
              onChange={(e) => onVersion(e.target.value)}
            />
          )}
        </ValueField>
        <ValueField
          path="metadata.description"
          label="Description"
          empty={!draft.description}
          problems={problems("metadata.description")}
          hint="Shown where people choose a flavor."
          className="sm:col-span-2"
        >
          {({ inputId, describedBy, invalid }) => (
            <input
              id={inputId}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              data-testid="spec-description-input"
              className={inputCls}
              placeholder="What clusters of this flavor are for"
              value={draft.description}
              onChange={(e) => onDescription(e.target.value)}
            />
          )}
        </ValueField>
      </div>

      <FieldGroup
        title="Owner and platform"
        description="Owners are numbers of 1 to 10 digits. Agent runs on bare-metal workers; KubeVirt on virtual machines."
      >
        <div className="grid gap-x-5 gap-y-4 sm:grid-cols-3">
          {OWNERS.map(({ path, label }) => {
            const value = draft.values[path];
            const text = value === undefined ? "" : String(value);
            return (
              <ValueField
                key={path}
                path={path}
                label={label}
                locked={isLocked(draft, path)}
                onLockedChange={(locked) => onLocked(path, locked)}
                notEnforced={notEnforced(path)}
                empty={!text}
                problems={problems(path)}
              >
                {({ inputId, describedBy, invalid }) => (
                  <input
                    id={inputId}
                    aria-describedby={describedBy}
                    aria-invalid={invalid}
                    className={cn(inputCls, "font-mono tabular")}
                    inputMode="numeric"
                    autoComplete="off"
                    maxLength={10}
                    placeholder="Not set"
                    value={text}
                    onChange={(e) => onValue(path, e.target.value === "" ? undefined : e.target.value)}
                  />
                )}
              </ValueField>
            );
          })}
        <ValueField
          path={PLATFORM}
          label="Platform"
          locked={isLocked(draft, PLATFORM)}
          onLockedChange={(locked) => onLocked(PLATFORM, locked)}
          notEnforced={notEnforced(PLATFORM)}
          empty={!platform}
          problems={problems(PLATFORM)}
          labelsInput={false}
        >
          {() => (
            <Segmented
              options={platformOptions}
              value={platform}
              onChange={(v) => onValue(PLATFORM, v === "" ? undefined : v)}
              label="Platform"
            />
          )}
        </ValueField>
        </div>
      </FieldGroup>

      {otherInputs.length > 0 && (
        <div className="space-y-3">
          <button
            type="button"
            aria-expanded={moreOpen}
            onClick={() => setMoreOpen((v) => !v)}
            className="group flex items-center gap-1.5 text-sm font-semibold"
          >
            <ChevronRight
              aria-hidden
              className={cn("h-4 w-4 text-muted-foreground transition-transform duration-200", moreOpen && "rotate-90")}
            />
            Other template inputs
            <span className="font-normal text-muted-foreground">
              · {setCount > 0 ? `${setCount} set` : `${otherInputs.length}`}, presets only
            </span>
          </button>
          {moreOpen && (
            <div className="grid gap-x-5 gap-y-4 pl-6 sm:grid-cols-2">
              {otherInputs.map((input) => (
                <PresetInput
                  key={input.name}
                  input={input}
                  path={input.name}
                  value={draft.values[input.name]}
                  onChange={(v) => onValue(input.name, v)}
                  problems={problems(input.name)}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
