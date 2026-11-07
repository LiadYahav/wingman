// ── RFC 9457 problems (ADR-0004) ─────────────────────────────────────────────
//
// Both services answer every error with `application/problem+json`. `code` is
// the stable member to match on; `title` and `detail` are for people and may
// change wording. The codes are append-only (wingman_core.web.errors).

export type ErrorCode =
  | "VALIDATION_ERROR"
  | "NOT_FOUND"
  | "ALREADY_EXISTS"
  | "REVISION_CONFLICT"
  | "NOT_MERGEABLE"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "GIT_UNAVAILABLE"
  | "GIT_PERMISSION_DENIED"
  | "GIT_REJECTED"
  | "AMBIGUOUS_WRITE"
  | "INTERNAL_ERROR"
  | "SELF_APPROVAL"
  | "FEATURE_DISABLED"
  | "DEPENDENCY_UNAVAILABLE";

/** One entry of FastAPI's own request validation (`details.errors`). */
export interface RequestFieldError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface ProblemDetails {
  /** Every rule a request broke (a service's own validation). */
  problems?: string[];
  /** FastAPI's request validation: a missing or malformed field. */
  errors?: RequestFieldError[];
  /** day2: the rule a refused write broke. */
  rule?: string;
  /** day2: the ids a bare cluster name matched. */
  candidates?: string[];
  [key: string]: unknown;
}

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  code: ErrorCode;
  request_id: string | null;
  details: ProblemDetails;
}
