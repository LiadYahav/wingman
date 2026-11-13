import { describe, expect, it } from "vitest";
import { isTyping } from "./keyboard";
import {
  COLLAPSED_ATTRIBUTE,
  SIDEBAR_SCRIPT,
  SIDEBAR_STORAGE_KEY,
  isSidebarShortcut,
  readCollapsed,
  sidebarShortcutLabel,
  writeCollapsed,
} from "./sidebar-rail";

/** A Storage stand-in: a map, or one that throws as a blocked localStorage does. */
function memoryStorage(initial: Record<string, string> = {}) {
  const items = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
    items,
  };
}
const blocked = {
  getItem: (): string | null => {
    throw new DOMException("denied", "SecurityError");
  },
  setItem: (): void => {
    throw new DOMException("full", "QuotaExceededError");
  },
};

const field = (tagName: string, isContentEditable = false) => ({ tagName, isContentEditable }) as unknown as EventTarget;
const key = (overrides: Partial<Parameters<typeof isSidebarShortcut>[0]> = {}) => ({
  key: "b",
  code: "KeyB",
  ctrlKey: true,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  repeat: false,
  target: field("BODY"),
  ...overrides,
});

describe("the stored preference", () => {
  it("is expanded unless the rail was chosen", () => {
    expect(readCollapsed(memoryStorage())).toBe(false);
    expect(readCollapsed(memoryStorage({ [SIDEBAR_STORAGE_KEY]: "expanded" }))).toBe(false);
    expect(readCollapsed(memoryStorage({ [SIDEBAR_STORAGE_KEY]: "nonsense" }))).toBe(false);
    expect(readCollapsed(memoryStorage({ [SIDEBAR_STORAGE_KEY]: "collapsed" }))).toBe(true);
  });

  it("round-trips both ways", () => {
    const storage = memoryStorage();
    expect(writeCollapsed(storage, true)).toBe(true);
    expect(storage.items.get(SIDEBAR_STORAGE_KEY)).toBe("collapsed");
    expect(readCollapsed(storage)).toBe(true);
    expect(writeCollapsed(storage, false)).toBe(true);
    expect(storage.items.get(SIDEBAR_STORAGE_KEY)).toBe("expanded");
    expect(readCollapsed(storage)).toBe(false);
  });

  it("falls back to expanded when storage is missing or throws, and says the write was not kept", () => {
    expect(readCollapsed(undefined)).toBe(false);
    expect(readCollapsed(blocked)).toBe(false);
    expect(writeCollapsed(undefined, true)).toBe(false);
    expect(writeCollapsed(blocked, true)).toBe(false);
  });
});

describe("the script that runs before the first paint", () => {
  /** Runs SIDEBAR_SCRIPT against a stand-in localStorage and <html>. */
  function run(storage: Pick<Storage, "getItem">) {
    const attributes = new Map<string, string>();
    const document = { documentElement: { setAttribute: (name: string, value: string) => void attributes.set(name, value) } };
    new Function("localStorage", "document", SIDEBAR_SCRIPT)(storage, document);
    return attributes;
  }

  it("marks <html> exactly when readCollapsed says the rail", () => {
    for (const value of ["collapsed", "expanded", "other"]) {
      const storage = memoryStorage({ [SIDEBAR_STORAGE_KEY]: value });
      expect(run(storage).has(COLLAPSED_ATTRIBUTE)).toBe(readCollapsed(storage));
    }
    expect(run(memoryStorage()).size).toBe(0);
  });

  it("never throws when storage is blocked", () => {
    expect(run(blocked).size).toBe(0);
  });
});

describe("the shortcut", () => {
  it("is Ctrl+B or ⌘B", () => {
    expect(isSidebarShortcut(key())).toBe(true);
    expect(isSidebarShortcut(key({ ctrlKey: false, metaKey: true }))).toBe(true);
    expect(isSidebarShortcut(key({ key: "B" }))).toBe(true);
  });

  it("is not B alone, another letter, an extra modifier or a held key", () => {
    expect(isSidebarShortcut(key({ ctrlKey: false }))).toBe(false);
    expect(isSidebarShortcut(key({ key: "k", code: "KeyK" }))).toBe(false);
    expect(isSidebarShortcut(key({ shiftKey: true }))).toBe(false);
    expect(isSidebarShortcut(key({ altKey: true }))).toBe(false);
    expect(isSidebarShortcut(key({ repeat: true }))).toBe(false);
  });

  it("follows the letter on a Latin layout and the key's place on any other", () => {
    // Dvorak: the B key's place types "x", and "b" is elsewhere
    expect(isSidebarShortcut(key({ key: "x", code: "KeyB" }))).toBe(false);
    expect(isSidebarShortcut(key({ key: "b", code: "KeyN" }))).toBe(true);
    // Hebrew: the B key types "נ"
    expect(isSidebarShortcut(key({ key: "נ", code: "KeyB" }))).toBe(true);
    expect(isSidebarShortcut(key({ key: "מ", code: "KeyN" }))).toBe(false);
  });

  it("never fires while typing in a field", () => {
    for (const tag of ["INPUT", "TEXTAREA", "SELECT"]) expect(isSidebarShortcut(key({ target: field(tag) }))).toBe(false);
    expect(isSidebarShortcut(key({ target: field("DIV", true) }))).toBe(false);
    expect(isSidebarShortcut(key({ target: field("BUTTON") }))).toBe(true);
    expect(isSidebarShortcut(key({ target: field("A") }))).toBe(true);
  });

  it("is written as the platform writes it", () => {
    expect(sidebarShortcutLabel("MacIntel")).toBe("⌘B");
    expect(sidebarShortcutLabel("iPad")).toBe("⌘B");
    expect(sidebarShortcutLabel("Win32")).toBe("Ctrl+B");
    expect(sidebarShortcutLabel("Linux x86_64")).toBe("Ctrl+B");
  });
});

describe("isTyping", () => {
  it("is a field or contenteditable, and nothing else", () => {
    expect(isTyping(field("INPUT"))).toBe(true);
    expect(isTyping(field("TEXTAREA"))).toBe(true);
    expect(isTyping(field("SPAN", true))).toBe(true);
    expect(isTyping(field("BODY"))).toBe(false);
    expect(isTyping(null)).toBe(false);
  });
});
