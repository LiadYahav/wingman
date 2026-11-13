"use client"

import * as React from "react"
import { Combobox as ComboboxPrimitive } from "@base-ui/react/combobox"
import { CheckIcon, SearchIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { DropdownChevron, dropdownTriggerClassName } from "@/components/ui/select"

/** One choice of a `Combobox`. */
export interface ComboboxOption {
  /** What `onValueChange` receives; unique within the options. */
  value: string
  label: string
  /** A second, muted line under the label. Searched too. */
  description?: string
  /** Options of one group are listed together under its name; ungrouped ones come first. */
  group?: string
  disabled?: boolean
}

interface OptionGroup {
  value: string
  items: ComboboxOption[]
}

/** The options in groups, in the order each group first appears; `null` when none has a group. */
function groupOptions(options: readonly ComboboxOption[]): OptionGroup[] | null {
  if (!options.some((option) => option.group)) return null
  const groups = new Map<string, ComboboxOption[]>([["", []]])
  for (const option of options) {
    const key = option.group ?? ""
    groups.set(key, [...(groups.get(key) ?? []), option])
  }
  return [...groups].filter(([, items]) => items.length > 0).map(([value, items]) => ({ value, items }))
}

/** Every word of the query appears in the option's label, description, group or value. */
function optionMatches(option: ComboboxOption, query: string): boolean {
  const text = [option.label, option.description, option.group, option.value].join(" ").toLowerCase()
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => text.includes(word))
}

const isSameOption = (a: ComboboxOption, b: ComboboxOption) => a.value === b.value

interface ComboboxProps {
  options: readonly ComboboxOption[]
  /** The chosen option's value; `null` or `""` shows the placeholder. */
  value: string | null
  onValueChange: (value: string | null) => void
  placeholder?: string
  /** The search box's placeholder and accessible name. */
  searchPlaceholder?: string
  /** Shown when no option matches the search. */
  emptyMessage?: string
  disabled?: boolean
  size?: "sm" | "default" | "lg"
  /** Classes for the trigger (the closed control). */
  className?: string
  id?: string
  "aria-label"?: string
  "aria-labelledby"?: string
  "aria-describedby"?: string
  "aria-invalid"?: boolean
  "data-testid"?: string
}

/**
 * A dropdown with a search box, for lists that can grow (sites, MCEs, infra
 * envs, chart revisions, versions). Closed it looks exactly like a `Select`.
 *
 * Keyboard: Enter, Space or ArrowDown on the trigger opens it with focus in
 * the search box; typing filters and highlights the first match; arrows move;
 * Enter chooses; Escape closes. The trigger is the `combobox` and takes the
 * accessible name and test id given here.
 */
function Combobox({
  options,
  value,
  onValueChange,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  emptyMessage = "No matches.",
  disabled,
  size = "default",
  className,
  ...triggerProps
}: ComboboxProps) {
  const groups = React.useMemo(() => groupOptions(options), [options])
  const selected = React.useMemo(
    () => (value ? (options.find((option) => option.value === value) ?? { value, label: value }) : null),
    [options, value]
  )

  return (
    <ComboboxPrimitive.Root<ComboboxOption>
      items={groups ?? options}
      value={selected}
      onValueChange={(option) => onValueChange(option?.value ?? null)}
      itemToStringLabel={(option) => option.label}
      itemToStringValue={(option) => option.value}
      isItemEqualToValue={isSameOption}
      filter={optionMatches}
      autoHighlight
      disabled={disabled}
    >
      <ComboboxPrimitive.Trigger
        data-slot="combobox-trigger"
        data-size={size}
        className={cn(dropdownTriggerClassName, "w-full", className)}
        {...triggerProps}
      >
        <span className="min-w-0 flex-1 truncate text-left">
          <ComboboxPrimitive.Value>
            {(option: ComboboxOption | null) => option?.label ?? placeholder}
          </ComboboxPrimitive.Value>
        </span>
        <ComboboxPrimitive.Icon render={<DropdownChevron />} />
      </ComboboxPrimitive.Trigger>
      <ComboboxPrimitive.Portal>
        <ComboboxPrimitive.Positioner side="bottom" align="start" sideOffset={4} className="isolate z-50">
          <ComboboxPrimitive.Popup
            data-slot="combobox-content"
            className="relative isolate z-50 flex max-h-[min(var(--available-height),24rem)] w-(--anchor-width) min-w-56 origin-(--transform-origin) flex-col overflow-hidden rounded-lg bg-popover text-popover-foreground shadow-md ring-1 ring-foreground/10 duration-100 data-[side=bottom]:slide-in-from-top-2 data-[side=top]:slide-in-from-bottom-2 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95"
          >
            <div className="flex shrink-0 items-center gap-2 border-b px-3">
              <SearchIcon className="pointer-events-none size-4 shrink-0 text-muted-foreground" />
              <ComboboxPrimitive.Input
                data-slot="combobox-input"
                placeholder={searchPlaceholder}
                aria-label={searchPlaceholder}
                className="h-9 w-full min-w-0 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              />
            </div>
            <ComboboxPrimitive.Empty className="px-3 py-6 text-center text-sm text-muted-foreground empty:hidden">
              {emptyMessage}
            </ComboboxPrimitive.Empty>
            <ComboboxPrimitive.List className="min-h-0 scroll-py-1 overflow-y-auto p-1 empty:hidden">
              {groups
                ? (group: OptionGroup) => (
                    <ComboboxPrimitive.Group key={group.value} items={group.items} className="not-first:mt-1">
                      {group.value && (
                        <ComboboxPrimitive.GroupLabel className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
                          {group.value}
                        </ComboboxPrimitive.GroupLabel>
                      )}
                      <ComboboxPrimitive.Collection>
                        {(option: ComboboxOption) => <ComboboxItem key={option.value} option={option} />}
                      </ComboboxPrimitive.Collection>
                    </ComboboxPrimitive.Group>
                  )
                : (option: ComboboxOption) => <ComboboxItem key={option.value} option={option} />}
            </ComboboxPrimitive.List>
          </ComboboxPrimitive.Popup>
        </ComboboxPrimitive.Positioner>
      </ComboboxPrimitive.Portal>
    </ComboboxPrimitive.Root>
  )
}

function ComboboxItem({ option }: { option: ComboboxOption }) {
  return (
    <ComboboxPrimitive.Item
      value={option}
      disabled={option.disabled}
      data-slot="combobox-item"
      className="relative flex w-full cursor-default items-start rounded-md py-1.5 pr-8 pl-2 text-sm outline-hidden select-none data-disabled:cursor-not-allowed data-disabled:opacity-50 data-highlighted:bg-accent data-highlighted:text-accent-foreground"
    >
      <span className="min-w-0 flex-1">
        <span className="block wrap-anywhere">{option.label}</span>
        {option.description && (
          <span className="mt-0.5 block text-xs wrap-anywhere text-muted-foreground">{option.description}</span>
        )}
      </span>
      <ComboboxPrimitive.ItemIndicator className="pointer-events-none absolute top-2 right-2 flex size-4 items-center justify-center">
        <CheckIcon className="size-4" />
      </ComboboxPrimitive.ItemIndicator>
    </ComboboxPrimitive.Item>
  )
}

export { Combobox }
