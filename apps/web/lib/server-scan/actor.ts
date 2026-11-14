/**
 * How server-scan names who did something: a person by their name, its
 * static API tokens as "API token (admin)", a personal token as its owner's,
 * the system as "System (<job>)". A Wingman write reaches server-scan with its
 * admin token, so it reads "API token (admin)"; Wingman's own log names the
 * person (docs/notes/2026-11-13-server-scan-area-api.md §8.5).
 *
 * Ported from team-redbull/server-scan at 92146d3, `frontend/src/lib/actor.ts`
 * (decision 18 of the single-pane plan).
 */

import type { Actor } from "@/types/server-scan-record";

export type ActorKind = "user" | "token" | "system";

const TOKEN_ID = /^api-token-(.+)$/;
const PERSONAL_TOKEN_ID = /^token:(.+)$/;

/** An actor id alone (a maintenance's `created_by`): a static token reads "API token (admin)", anything else is the id. */
export function actorIdLabel(id: string): string {
  const personal = PERSONAL_TOKEN_ID.exec(id);
  if (personal) return `${personal[1] ?? ""} (personal token)`;
  const token = TOKEN_ID.exec(id);
  return token ? `API token (${token[1] ?? ""})` : id;
}

/** How an actor is shown everywhere: the words, and the user / token / system chip beside them. */
export function actorLabel(actor: Actor): { label: string; kind: ActorKind } {
  if (actor.type === "SYSTEM") return { label: `System (${actor.id})`, kind: "system" };
  if (actor.type === "TOKEN") return { label: actorIdLabel(actor.id), kind: "token" };
  return { label: actor.display ?? actor.id, kind: "user" };
}
