"use client";

import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { fieldInputClassName, type FieldInputContext, type FieldValue, type FormValues } from "@/components/clusters/dynamic-variable-form";
import { DROP_MCE_MIRRORS, IMAGE_MIRRORS, asMirrorEntries, dropsMceMirrors, noMirrorsProblem } from "@/lib/image-mirrors";
import { KeepMceMirrorsSwitch, MirrorEntriesEditor, MirrorEntryList } from "./mirror-entries";

/**
 * The create form's image mirrors (ADR-0063), drawn by path instead of the
 * generic list and text editors: the flavor's entries, editable when they are
 * a preset and shown when locked, and the MCE default mirrors as a switch
 * that sends a JSON boolean. `undefined` for any other field.
 */
export function mirrorCreateInput({ path, value, onChange, locked }: FieldInputContext, form: FormValues): ReactNode | undefined {
  if (path === IMAGE_MIRRORS) {
    const entries = asMirrorEntries(value);
    if (locked) return <MirrorEntryList entries={entries} testId="create-mirror-list" />;
    return (
      <div className="space-y-1">
        {entries.length === 0 && (
          <p className="text-xs text-muted-foreground">None: the MCE&apos;s default mirrors apply, and nothing is written.</p>
        )}
        <MirrorEntriesEditor
          entries={entries}
          onChange={(next) => onChange(next as unknown as FieldValue)}
          inputClassName={fieldInputClassName}
          label="Image mirrors"
          testId="create-mirror-entries"
        />
      </div>
    );
  }
  if (path !== DROP_MCE_MIRRORS) return undefined;
  const none = noMirrorsProblem(form);
  return (
    <div className="space-y-1.5">
      <KeepMceMirrorsSwitch
        keep={!dropsMceMirrors(value)}
        onChange={(keep) => onChange(!keep)}
        disabled={locked}
        testId="create-keep-mce-mirrors"
      />
      {none && (
        <p className="flex items-start gap-1.5 text-xs text-status-warning-fg" data-testid="create-no-mirrors">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          {none}
        </p>
      )}
    </div>
  );
}
