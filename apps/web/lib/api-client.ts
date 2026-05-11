/**
 * API client for Wingman backend services.
 *
 * Routes:
 *   /api/auth/*  → day1-service (auth)
 *   /api/day1/*  → day1-service
 *   /api/day2/*  → day2-service
 *
 * All requests include the JWT from the auth store in the Authorization header.
 * On 401, clears auth and redirects to /login.
 */

import Cookies from "js-cookie";

const TOKEN_COOKIE = "wingman-token";

function getToken(): string | null {
  return Cookies.get(TOKEN_COOKIE) ?? null;
}

function setToken(token: string): void {
  // httpOnly is not settable from JS — we use a regular cookie here.
  // The middleware checks for this cookie server-side.
  Cookies.set(TOKEN_COOKIE, token, {
    secure: window.location.protocol === "https:",
    sameSite: "strict",
    expires: 1, // 1 day — will be refreshed by JWT expiry logic
  });
}

function clearToken(): void {
  Cookies.remove(TOKEN_COOKIE);
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(path, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    // Also clear zustand auth store so login page doesn't redirect back immediately
    try {
      localStorage.removeItem("wingman-auth");
    } catch { /* ignore */ }
    window.location.href = "/login";
    throw new Error("Unauthorized — redirecting to login");
  }

  if (!res.ok) {
    const body = await res.text();
    let message = `API error ${res.status}: ${body}`;
    try {
      const json = JSON.parse(body);
      if (typeof json?.detail === "string") message = json.detail;
    } catch { /* use raw body */ }
    throw new Error(message);
  }

  // Handle empty responses (204 No Content)
  if (res.status === 204) return undefined as T;

  return res.json() as Promise<T>;
}

async function requestText(
  path: string,
  options: RequestInit = {}
): Promise<string> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(path, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    try {
      localStorage.removeItem("wingman-auth");
    } catch { /* ignore */ }
    window.location.href = "/login";
    throw new Error("Unauthorized — redirecting to login");
  }

  if (!res.ok) {
    const body = await res.text();
    let message = `API error ${res.status}: ${body}`;
    try {
      const json = JSON.parse(body);
      if (typeof json?.detail === "string") message = json.detail;
    } catch { /* use raw body */ }
    throw new Error(message);
  }

  return res.text();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  getText: (path: string) => requestText(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export { getToken, setToken, clearToken };
