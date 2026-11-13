/** Elements whose keys are text: a page's shortcut never fires while one has focus. */
const FIELDS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/**
 * Typing in a field (an input, a textarea, a select or anything
 * contenteditable): a key there is a character, not a page's shortcut.
 * Duck-typed on `tagName` and `isContentEditable`, so it needs no DOM to test.
 */
export function isTyping(target: EventTarget | null): boolean {
  if (target === null || typeof target !== "object") return false;
  const element = target as { tagName?: unknown; isContentEditable?: unknown };
  return element.isContentEditable === true || (typeof element.tagName === "string" && FIELDS.has(element.tagName));
}
