/**
 * Vitest: unit tests for the web's pure logic (filters, sorting, URL state,
 * CSV), next to the code as `*.test.ts`. Node only, no DOM: what a page shows
 * is Playwright's (e2e/). Never part of the Next build: nothing the app
 * imports reaches a test file.
 */

import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: {
    include: ["lib/**/*.test.ts", "components/**/*.test.ts"],
    environment: "node",
  },
});
