"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { isApiError } from "@/lib/api-client";
import { day1Api } from "@/lib/api/day1";
import { useAuthStore } from "@/stores/auth-store";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type DevRole = "admin" | "viewer";

/** The roles a dev login can ask for; `items` lets the trigger show the label, not the value. */
const ROLES: { value: DevRole; label: string }[] = [
  { value: "viewer", label: "Viewer" },
  { value: "admin", label: "Admin" },
];

/** The day1 service's rule for dev-login usernames (application/auth.py). */
const DEV_USERNAME = /^[a-z0-9]([a-z0-9._-]{0,62}[a-z0-9])?$/;

/** Only same-site paths: `?redirect=` must never send the browser elsewhere. */
function safeRedirect(target: string | null): string {
  return target && target.startsWith("/") && !target.startsWith("//") ? target : "/";
}

function callbackError(err: unknown): string {
  if (isApiError(err, "FORBIDDEN")) return "You are not in a Wingman group. Ask an admin for access.";
  if (isApiError(err, "UNAUTHORIZED")) return "OpenShift refused the login. Please try again.";
  if (isApiError(err, "DEPENDENCY_UNAVAILABLE")) return "OpenShift could not be reached. Please try again shortly.";
  return "Authentication failed. Please try again.";
}

function devLoginError(err: unknown): string {
  if (isApiError(err, "UNAUTHORIZED")) return "The dev login secret is wrong.";
  if (isApiError(err, "NOT_FOUND")) return "Dev login is turned off on this server.";
  if (isApiError(err, "VALIDATION_ERROR")) return err.messages().join(" · ");
  return "Dev login failed. Is the day1 service running?";
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, isAuthenticated } = useAuthStore();

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devAuthEnabled, setDevAuthEnabled] = useState(false);
  const [devUsername, setDevUsername] = useState("");
  const [devSecret, setDevSecret] = useState("");
  const [devRole, setDevRole] = useState<DevRole>("viewer");

  useEffect(() => {
    const code = searchParams.get("code");
    if (!code) return;

    const exchangeCode = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await day1Api.auth.callback(code);
        login(data.access_token, data.user);
        router.replace(safeRedirect(searchParams.get("redirect")));
      } catch (err) {
        setError(callbackError(err));
      } finally {
        setIsLoading(false);
      }
    };

    exchangeCode();
  }, [searchParams, login, router]);

  useEffect(() => {
    if (isAuthenticated && !searchParams.get("code")) {
      router.replace(safeRedirect(searchParams.get("redirect")));
    }
  }, [isAuthenticated, searchParams, router]);

  useEffect(() => {
    day1Api.auth.config()
      .then((cfg) => { if (cfg.dev_auth_enabled) setDevAuthEnabled(true); })
      .catch(() => {});
  }, []);

  const handleLogin = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const config = await day1Api.auth.config();
      window.location.href = config.authorize_url;
    } catch {
      setError("Could not reach the authentication server. Please try again.");
      setIsLoading(false);
    }
  };

  const username = devUsername.trim();
  const usernameInvalid = username !== "" && !DEV_USERNAME.test(username);

  const handleDevLogin = async () => {
    if (!username) { setError("Username is required"); return; }
    if (usernameInvalid) { setError("Usernames are lowercase letters, digits, '.', '_' and '-'"); return; }
    if (!devSecret) { setError("The dev login secret is required (DEV_AUTH_SECRET)"); return; }
    setIsLoading(true);
    setError(null);
    try {
      const data = await day1Api.auth.devLogin({ username, role: devRole, secret: devSecret });
      // The isAuthenticated effect above navigates once the store updates.
      login(data.access_token, data.user);
    } catch (err) {
      setError(devLoginError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const isCallbackLoading = Boolean(searchParams.get("code")) && isLoading;

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      {/* Subtle grid background */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#0073ea08_1px,transparent_1px),linear-gradient(to_bottom,#0073ea08_1px,transparent_1px)] bg-[size:64px_64px] pointer-events-none" />

      <div className="relative w-full max-w-sm space-y-8 px-4">
        {/* Branding — Echelon lockup */}
        <div className="flex flex-col items-center gap-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/wingman-logo.svg"
            alt="Wingman"
            width={96}
            height={96}
            className="rounded-2xl shadow-xl shadow-black/30"
          />
          <div className="text-center space-y-1.5">
            <h1
              className="text-[52px] leading-none text-foreground"
              style={{ fontFamily: "var(--font-grotesk, var(--font-heading))", fontWeight: 500, letterSpacing: "-0.035em" }}
            >
              Wing<span style={{ color: "#5b78b8" }}>man</span>
            </h1>
            <p
              className="text-[11px] tracking-[0.18em] uppercase text-muted-foreground"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              Internal Developer Platform
            </p>
          </div>
        </div>

        {/* Card */}
        <div className="rounded-2xl border bg-card shadow-sm p-6 space-y-5">
          {devAuthEnabled && (
            <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 px-3 py-2 text-xs text-amber-700 dark:text-amber-400 font-medium">
              Dev mode — sign in with any username and the server&apos;s dev login secret
            </div>
          )}

          {error && (
            <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2.5 text-sm text-destructive">
              {error}
            </div>
          )}

          {isCallbackLoading ? (
            <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
              <Spinner />
              Signing you in&hellip;
            </div>
          ) : devAuthEnabled ? (
            <form
              className="space-y-3"
              onSubmit={(e) => { e.preventDefault(); handleDevLogin(); }}
            >
              <div className="space-y-1">
                <input
                  type="text"
                  placeholder="Username"
                  aria-label="Username"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  value={devUsername}
                  onChange={(e) => setDevUsername(e.target.value)}
                  aria-invalid={usernameInvalid}
                  className="w-full rounded-lg border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow aria-invalid:border-destructive/60"
                />
                {usernameInvalid && (
                  <p className="text-xs text-destructive">
                    Lowercase letters, digits, &apos;.&apos;, &apos;_&apos; and &apos;-&apos;; start and end with a letter or digit.
                  </p>
                )}
              </div>
              <input
                type="password"
                placeholder="Dev login secret"
                aria-label="Dev login secret"
                autoComplete="current-password"
                value={devSecret}
                onChange={(e) => setDevSecret(e.target.value)}
                className="w-full rounded-lg border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow"
              />
              <Select value={devRole} onValueChange={(role) => role && setDevRole(role)} items={ROLES}>
                <SelectTrigger size="lg" className="w-full" aria-label="Role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {ROLES.map((role) => (
                    <SelectItem key={role.value} value={role.value}>{role.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <button
                type="submit"
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary/90 active:scale-[0.98] transition-all disabled:opacity-60"
                disabled={isLoading}
              >
                {isLoading ? <><Spinner />Signing in&hellip;</> : "Sign in"}
              </button>
            </form>
          ) : (
            <button
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3 text-sm font-semibold text-white hover:bg-primary/90 active:scale-[0.98] transition-all disabled:opacity-60 shadow-sm shadow-primary/25"
              onClick={handleLogin}
              disabled={isLoading}
            >
              {isLoading ? (
                <><Spinner />Connecting&hellip;</>
              ) : (
                "Log in via OpenShift"
              )}
            </button>
          )}
        </div>

        {!devAuthEnabled && (
          <p className="text-center text-xs text-muted-foreground">
            You will be redirected to your organization&apos;s OpenShift OAuth server.
          </p>
        )}
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginContent />
    </Suspense>
  );
}
