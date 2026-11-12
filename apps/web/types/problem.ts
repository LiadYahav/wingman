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
  | "DEPENDENCY_UNAVAILABLE"
  /** 409: neither a Machine of the cluster nor server-scan places the server in it (an uninstall). */
  | "NODE_NOT_IN_CLUSTER"
  /** 409: the orchestrator already runs an uninstall of this server. */
  | "UNINSTALL_ALREADY_RUNNING"
  /** 403: a day2 team has not given Wingman's GitLab account write access to its project (ADR-0043). */
  | "TEAM_READ_ONLY";

/** One entry of FastAPI's own request validation (`details.errors`). */
export interface RequestFieldError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/** One item a day2 bulk install refused: the item and why. */
export interface ProblemItem {
  team?: string;
  chart?: string;
  detail?: string;
  [key: string]: unknown;
}

export interface ProblemDetails {
  /** Every rule a request broke: day1 sends sentences, day2's bulk install one item each. */
  problems?: (string | ProblemItem)[];
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
