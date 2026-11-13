import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // A disable comment that no longer suppresses anything fails lint, so a
  // size exemption (below) falls away once its function is split.
  {
    linterOptions: { reportUnusedDisableDirectives: "error" },
  },
  // Functions stay small (ADR-0056). Existing offenders carry a per-function
  // `eslint-disable-next-line ... -- baseline (ADR-0056)`; never add one.
  // Not e2e (a describe block is long by nature; the file-size check covers
  // tests) and not components/ui (shadcn's generated components).
  {
    files: ["**/*.{ts,tsx}"],
    ignores: ["e2e/**", "components/ui/**"],
    rules: {
      "max-lines-per-function": [
        "error",
        { max: 200, skipBlankLines: true, skipComments: true },
      ],
      complexity: ["error", 30],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Playwright's local output (bundled trace viewer, run artifacts).
    "playwright-report/**",
    "test-results/**",
  ]),
]);

export default eslintConfig;
