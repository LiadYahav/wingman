// Types of the day1 service (`/api/day1`), from its Pydantic schemas in
// apps/day1-service/src/wingman_day1/api/v1/*schemas.py. Every web-visible
// change is listed in docs/notes/2026-11-07-day1-api-changes.md and, for
// flavors v2, docs/notes/2026-11-08-flavors-v2-api-changes.md (the "§n" in
// these files); a flavor's rollout, one MR per cluster:
// docs/notes/2026-11-12-flavor-rollout-api.md.
//
// One file per section. This index re-exports them all, so `@/types` stays
// the one import path (ADR-0056).

export * from "./specs";
export * from "./machine-configs";
export * from "./sites";
export * from "./placement";
export * from "./clusters";
export * from "./live-status";
export * from "./drift";
export * from "./rollout";
export * from "./import-clusters";
export * from "./sync";
export * from "./workflows";
export * from "./nodes";
