"use client";

import { KeepMceMirrorsSwitch, MirrorEntriesEditor } from "@/components/image-mirrors/mirror-entries";
import {
  DROP_MCE_MIRRORS,
  IMAGE_MIRRORS,
  asMirrorEntries,
  dropsMceMirrors,
  readableMirrorProblem,
  type MirrorEntry,
} from "@/lib/image-mirrors";
import { FieldGroup, inputCls, ValueField } from "./controls";
import { isLocked, type FlavorDraft } from "./model";

/**
 * The flavor's image mirrors (ADR-0063), optional: the cluster's own
 * mirrors, and whether the MCE's default mirrors are kept. Each is a preset
 * or locked as a whole. Unset, nothing is written: a cluster gets the MCE's
 * default mirrors, as before.
 */
export function ImageMirrorsGroup({
  draft,
  problems,
  notEnforced,
  onValue,
  onLocked,
}: {
  draft: FlavorDraft;
  problems: (path: string, options?: { deeper?: boolean }) => string[];
  notEnforced: (path: string) => string | undefined;
  onValue: (key: string, value: unknown) => void;
  onLocked: (path: string, locked: boolean) => void;
}) {
  const listValue = draft.values[IMAGE_MIRRORS];
  const entries = asMirrorEntries(listValue);
  const listLocked = isLocked(draft, IMAGE_MIRRORS);
  const dropValue = draft.values[DROP_MCE_MIRRORS];
  const dropLocked = isLocked(draft, DROP_MCE_MIRRORS);
  const keep = !dropsMceMirrors(dropValue);

  // Unlocked and emptied, the key goes (absent is the default); locked, an empty list is a value
  const setEntries = (next: MirrorEntry[]) => onValue(IMAGE_MIRRORS, next.length > 0 || listLocked ? next : undefined);
  const lockList = (locked: boolean) => {
    onLocked(IMAGE_MIRRORS, locked);
    if (locked && listValue === undefined) onValue(IMAGE_MIRRORS, []);
    if (!locked && entries.length === 0) onValue(IMAGE_MIRRORS, undefined);
  };
  const setKeep = (on: boolean) => onValue(DROP_MCE_MIRRORS, on ? (dropLocked ? false : undefined) : true);
  const lockDrop = (locked: boolean) => {
    onLocked(DROP_MCE_MIRRORS, locked);
    if (locked && dropValue === undefined) onValue(DROP_MCE_MIRRORS, false);
    if (!locked && dropValue === false) onValue(DROP_MCE_MIRRORS, undefined);
  };

  const listHint = listLocked
    ? entries.length > 0
      ? "Fixed: every cluster gets exactly these mirrors."
      : "Locked empty: no cluster gets mirrors of its own."
    : entries.length > 0
      ? "Prefilled: a cluster may change them."
      : "None: nothing is written, and the MCE's default mirrors apply. A cluster may add its own.";

  return (
    <FieldGroup
      title="Image mirrors"
      description="Optional. Registry mirrors of the cluster's own, for teams that pull operators and images from their own registry. They go to the cluster file's imageContentSources, merged with the MCE's default mirrors unless those are dropped."
    >
      <div className="space-y-4" data-testid="flavor-image-mirrors">
        <ValueField
          path={IMAGE_MIRRORS}
          label="The cluster's own mirrors"
          locked={listLocked}
          onLockedChange={lockList}
          notEnforced={notEnforced(IMAGE_MIRRORS)}
          empty={entries.length === 0}
          problems={problems(IMAGE_MIRRORS, { deeper: true }).map(readableMirrorProblem)}
          hint={listHint}
          labelsInput={false}
        >
          {({ describedBy, invalid }) => (
            <MirrorEntriesEditor
              entries={entries}
              onChange={setEntries}
              inputClassName={inputCls}
              label="Image mirrors"
              invalid={invalid}
              describedBy={describedBy}
              testId="flavor-mirror-entries"
            />
          )}
        </ValueField>
        <ValueField
          path={DROP_MCE_MIRRORS}
          label="MCE default mirrors"
          locked={dropLocked}
          onLockedChange={lockDrop}
          notEnforced={notEnforced(DROP_MCE_MIRRORS)}
          empty={dropValue === undefined}
          problems={problems(DROP_MCE_MIRRORS)}
          hint={
            dropLocked
              ? keep
                ? "Fixed: every cluster keeps the MCE's default mirrors."
                : "Fixed: every cluster drops the MCE's default mirrors."
              : dropValue === undefined
                ? "Not set: kept, as before. A cluster may drop them."
                : "Prefilled: a cluster may change it."
          }
          labelsInput={false}
        >
          {() => <KeepMceMirrorsSwitch keep={keep} onChange={setKeep} testId="flavor-keep-mce-mirrors" />}
        </ValueField>
      </div>
    </FieldGroup>
  );
}
