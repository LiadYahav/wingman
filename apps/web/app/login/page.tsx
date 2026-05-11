"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import { UserInfo } from "@/types";

interface AuthCallbackResponse {
  access_token: string;
  token_type: string;
  user: UserInfo;
}

interface AuthConfigResponse {
  authorize_url: string;
  dev_auth_enabled?: boolean;
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
  const [devRole, setDevRole] = useState<"admin" | "viewer">("viewer");

  useEffect(() => {
    const code = searchParams.get("code");
    if (!code) return;

    const exchangeCode = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await api.post<AuthCallbackResponse>("/api/auth/callback", { code });
        login(data.access_token, data.user);
        const redirect = searchParams.get("redirect") ?? "/";
        router.replace(redirect);
      } catch (err) {
        setError("Authentication failed. Please try again.");
        console.error("OAuth callback error:", err);
      } finally {
        setIsLoading(false);
      }
    };

    exchangeCode();
  }, [searchParams, login, router]);

  useEffect(() => {
    if (isAuthenticated && !searchParams.get("code")) {
      router.replace("/");
    }
  }, [isAuthenticated, searchParams, router]);

  useEffect(() => {
    api.get<AuthConfigResponse>("/api/auth/config")
      .then((cfg) => { if (cfg.dev_auth_enabled) setDevAuthEnabled(true); })
      .catch(() => {});
  }, []);

  const handleLogin = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const config = await api.get<AuthConfigResponse>("/api/auth/config");
      window.location.href = config.authorize_url;
    } catch {
      setError("Could not reach the authentication server. Please try again.");
      setIsLoading(false);
    }
  };

  const handleDevLogin = async () => {
    if (!devUsername.trim()) { setError("Username is required"); return; }
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.post<AuthCallbackResponse>("/api/auth/dev-login", {
        username: devUsername.trim(),
        role: devRole,
      });
      login(data.access_token, data.user);
      router.replace("/");
    } catch {
      setError("Dev login failed.");
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
            width={80}
            height={80}
            className="rounded-2xl shadow-xl shadow-black/30"
          />
          <div className="text-center space-y-1.5">
            <h1
              className="text-[42px] leading-none text-foreground"
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
              Dev mode — enter any username to sign in
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
            <div className="space-y-3">
              <input
                type="text"
                placeholder="Username"
                value={devUsername}
                onChange={(e) => setDevUsername(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleDevLogin()}
                className="w-full rounded-lg border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow"
              />
              <select
                value={devRole}
                onChange={(e) => setDevRole(e.target.value as "admin" | "viewer")}
                className="w-full rounded-lg border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow"
              >
                <option value="viewer">Viewer</option>
                <option value="admin">Admin</option>
              </select>
              <button
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary/90 active:scale-[0.98] transition-all disabled:opacity-60"
                onClick={handleDevLogin}
                disabled={isLoading}
              >
                {isLoading ? <><Spinner />Signing in&hellip;</> : "Sign in"}
              </button>
            </div>
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
