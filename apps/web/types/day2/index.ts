// The day2 service's response and request bodies, field for field with
// apps/day2-service/src/wingman_day2/api/v1/*schemas.py (the truth when these
// files and the service disagree). What changed for the web app, and why, is in
// docs/notes/2026-11-07-day2-api-changes.md and ADRs 0020-0024.
//
// One file per section. This index re-exports them all, so `@/types` (and
// the older `@/types/day2`) resolve as before (ADR-0056).

export * from "./destinations";
export * from "./teams";
export * from "./sync-options";
export * from "./catalog";
export * from "./charts";
export * from "./values-preview";
export * from "./writes";
export * from "./authoring";
export * from "./addons";
