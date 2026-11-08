/**
 * API client for Wingman backend services.
 *
 * Routes:
 *   /api/auth/*  → day1-service (auth)
 *   /api/day1/*  → day1-service
 *   /api/day2/*  → day2-service
 *
 * All requests include the JWT from the session cookie in the Authorization
 * header. On 401 the session is cleared and the browser goes to /login
 * (except for the login calls themselves, which opt out).
 *
 * Errors are RFC 9457 problems (ADR-0004) and are thrown as `ApiError`:
 * `message` is the problem's `detail`, `code` is what to match on, and
 * `messages()` lists every broken rule a form should show.
 */

import Cookies from "js-cookie";
import type { ErrorCode, Problem, ProblemDetails, ProblemItem, RequestFieldError } from "@/types/problem";

const TOKEN_COOKIE = "wingman-token";

function getToken(): string | null {
  return Cookies.get(TOKEN_COOKIE) ?? null;
}

function setToken(token: string): void {
  // httpOnly is not settable from JS — we use a regular cookie here.
  // The proxy checks for this cookie server-side.
  Cookies.set(TOKEN_COOKIE, token, {
    secure: window.location.protocol === "https:",
    sameSite: "strict",
    expires: 1, // 1 day — the JWT's own expiry is shorter
  });
}

function clearToken(): void {
  Cookies.remove(TOKEN_COOKIE);
}

/**
 * An error response from a Wingman service. The problem's members are own
 * fields (`status`, `code`, `detail`, `details`, `request_id`), so any reader
 * of the error sees them; `problem` is the body as received.
 */
export class ApiError extends Error {
  readonly status: number;
  /** The stable member to match on; `null` when the response was not a problem (a proxy's HTML page). */
  readonly code: ErrorCode | null;
  /** The problem's human message (also `message`). */
  readonly detail: string;
  readonly details: ProblemDetails;
  readonly request_id: string | null;
  /** The problem body, or `null` when the response was not a problem. */
  readonly problem: Problem | null;

  constructor(status: number, problem: Problem | null, fallback: string) {
    super(problem?.detail || fallback);
    this.name = "ApiError";
    this.status = status;
    this.code = problem?.code ?? null;
    this.detail = this.message;
    this.details = problem?.details ?? {};
    this.request_id = problem?.request_id ?? null;
    this.problem = problem;
  }

  get requestId(): string | null {
    return this.request_id;
  }

  /** `details.problems`: every rule the request broke, one line each. */
  get problems(): string[] {
    const problems = this.details.problems;
    return Array.isArray(problems) ? problems.map(formatProblem) : [];
  }

  /** `details.errors`: FastAPI's field-level validation errors. */
  get fieldErrors(): RequestFieldError[] {
    const errors = this.details.errors;
    return Array.isArray(errors) ? errors : [];
  }

  /** Everything a form should list: each broken rule, each bad field, or else the detail. */
  messages(): string[] {
    const lines = [...this.problems, ...this.fieldErrors.map(formatFieldError)];
    return lines.length > 0 ? lines : [this.message];
  }
}

/**
 * One `details.problems` entry as a line. day1 sends sentences; day2's bulk
 * install sends `{team, chart, detail, ...}` per refused item, shown as
 * `team/chart: detail`.
 */
function formatProblem(entry: unknown): string {
  if (typeof entry === "string") return entry;
  if (typeof entry !== "object" || entry === null) return String(entry);
  const item = entry as ProblemItem;
  if (typeof item.detail !== "string") return JSON.stringify(entry);
  const subject = [item.team, item.chart].filter((part) => typeof part === "string" && part).join("/");
  return subject ? `${subject}: ${item.detail}` : item.detail;
}

/** `["body", "variables", "x"]` → `variables.x: <msg>`. */
function formatFieldError(error: RequestFieldError): string {
  const loc = error.loc.filter((part, i) => !(i === 0 && ["body", "query", "path"].includes(String(part))));
  return loc.length > 0 ? `${loc.join(".")}: ${error.msg}` : error.msg;
}

function isProblem(value: unknown): value is Problem {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Problem).code === "string" &&
    typeof (value as Problem).detail === "string"
  );
}

/** Narrow an unknown error, optionally to one problem code or HTTP status. */
export function isApiError(error: unknown, match?: ErrorCode | number): error is ApiError {
  if (!(error instanceof ApiError)) return false;
  if (match === undefined) return true;
  return typeof match === "number" ? error.status === match : error.code === match;
}

/** Lines to show for any error: an ApiError's `messages()`, else the error's message. */
export function errorMessages(error: unknown): string[] {
  if (error instanceof ApiError) return error.messages();
  return [error instanceof Error ? error.message : String(error)];
}

interface RequestOptions extends RequestInit {
  /** Send the browser to /login on a 401 (default). The login calls turn it off. */
  redirectOnUnauthorized?: boolean;
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const { redirectOnUnauthorized = true, ...init } = options;
  const token = getToken();
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(path, { ...init, headers });
  if (res.ok) return res;

  const body = await res.text();
  let problem: Problem | null = null;
  try {
    const json: unknown = JSON.parse(body);
    if (isProblem(json)) problem = json;
  } catch { /* not JSON: keep the raw body for the message */ }
  const error = new ApiError(res.status, problem, `API error ${res.status}: ${body.slice(0, 200)}`);

  if (res.status === 401 && redirectOnUnauthorized) {
    clearToken();
    // Also clear the persisted auth store so the login page doesn't bounce back
    try {
      localStorage.removeItem("wingman-auth");
    } catch { /* storage unavailable */ }
    window.location.assign(new URL("/login", window.location.origin));
  }
  throw error;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const res = await send(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers as Record<string, string>) },
  });
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function requestText(path: string, options: RequestOptions = {}): Promise<string> {
  return (await send(path, options)).text();
}

type CallOptions = Pick<RequestOptions, "redirectOnUnauthorized">;

function withBody(method: string, body: unknown, options?: CallOptions): RequestOptions {
  return { ...options, method, body: body === undefined ? undefined : JSON.stringify(body) };
}

export const api = {
  get: <T>(path: string, options?: CallOptions) => request<T>(path, options),
  getText: (path: string) => requestText(path),
  post: <T>(path: string, body?: unknown, options?: CallOptions) =>
    request<T>(path, withBody("POST", body, options)),
  put: <T>(path: string, body?: unknown) => request<T>(path, withBody("PUT", body)),
  patch: <T>(path: string, body?: unknown) => request<T>(path, withBody("PATCH", body)),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export { getToken, setToken, clearToken };
