"use client";

import { useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import { Sun, Moon, Monitor, Shield, Eye, Users, AlertTriangle } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { cn } from "@/lib/utils";
import type { ServiceBuild } from "@/types";

const SERVICES = ["day1", "day2"] as const;

const noSubscription = () => () => {};

/**
 * False during the server render and the hydration pass, true after. The
 * theme is only known in the browser (next-themes reads localStorage and the
 * OS), so the selection is drawn only once mounted, or the server's HTML and
 * the client's first render would disagree.
 */
function useMounted(): boolean {
  return useSyncExternalStore(noSubscription, () => true, () => false);
}

function useBuild(service: (typeof SERVICES)[number]) {
  // staleTime 0: a restored cache entry must not hide a redeploy.
  return useQuery<ServiceBuild>({ queryKey: day1Keys.build(service), queryFn: () => day1Api.build(service), staleTime: 0 });
}

function BuildValue({ name, build, isPending, isError }: { name: string; build?: ServiceBuild; isPending: boolean; isError: boolean }) {
  if (isPending) return <span className="text-muted-foreground" data-testid={`build-${name}`}>…</span>;
  if (isError || !build) return <span className="text-muted-foreground" data-testid={`build-${name}`}>Could not be read</span>;
  return (
    <span className="font-medium" data-testid={`build-${name}`}>
      {build.version}
      {build.commit !== "unknown" && (
        <span className="ml-2 font-mono text-xs text-muted-foreground">{build.commit.slice(0, 12)}</span>
      )}
    </span>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
      <div className="px-5 py-3.5 border-b bg-muted/20">
        <h2 className="text-sm font-semibold">{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function ThemeOption({
  value, label, icon: Icon, current, onClick,
}: {
  value: string; label: string; icon: React.ElementType; current: string | undefined; onClick: () => void;
}) {
  const isActive = current === value;
  return (
    <button
      onClick={onClick}
      aria-pressed={isActive}
      className={cn(
        "flex flex-col items-center gap-2 rounded-xl border-2 p-4 transition-all w-28",
        isActive
          ? "border-primary bg-primary/5 dark:bg-primary/10"
          : "border-border hover:border-primary/40 hover:bg-muted/50"
      )}
    >
      <Icon className={cn("h-5 w-5", isActive ? "text-primary" : "text-muted-foreground")} />
      <span className={cn("text-xs font-medium", isActive ? "text-primary" : "text-muted-foreground")}>
        {label}
      </span>
    </button>
  );
}

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const mounted = useMounted();
  const current = mounted ? theme : undefined;
  const { user } = useAuthStore();
  const day1 = useBuild(SERVICES[0]);
  const day2 = useBuild(SERVICES[1]);
  const builds = [day1, day2];
  const skew = day1.data && day2.data && day1.data.version !== day2.data.version;

  return (
    <div className="p-6 lg:p-8 max-w-2xl mx-auto space-y-6">
      <div>
        <h1
          className="text-2xl font-bold tracking-tight"
          style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
        >
          Settings
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">Manage your preferences</p>
      </div>

      {/* Appearance */}
      <SectionCard title="Appearance">
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">Choose your preferred color theme.</p>
          <div className="flex gap-3">
            <ThemeOption value="light" label="Light" icon={Sun} current={current} onClick={() => setTheme("light")} />
            <ThemeOption value="dark" label="Dark" icon={Moon} current={current} onClick={() => setTheme("dark")} />
            <ThemeOption value="system" label="System" icon={Monitor} current={current} onClick={() => setTheme("system")} />
          </div>
        </div>
      </SectionCard>

      {/* Account */}
      {user && (
        <SectionCard title="Account">
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-white font-bold text-sm shrink-0">
                {user.username.charAt(0).toUpperCase()}
              </div>
              <div>
                <p className="font-semibold text-sm">{user.username}</p>
                {user.full_name && <p className="text-xs text-muted-foreground">{user.full_name}</p>}
                <div className="flex items-center gap-1.5 mt-1">
                  {user.role === "admin" ? (
                    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-primary/8 text-primary dark:bg-primary/20">
                      <Shield className="h-3 w-3" />Admin
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
                      <Eye className="h-3 w-3" />Viewer
                    </span>
                  )}
                </div>
              </div>
            </div>

            {user.groups && user.groups.length > 0 && (
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Users className="h-3.5 w-3.5" />
                  <span>Groups</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {user.groups.map((g) => (
                    <span key={g} className="rounded-full px-2.5 py-0.5 text-xs bg-muted text-muted-foreground font-medium">
                      {g}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </SectionCard>
      )}

      {/* Platform info: what each service reports it runs */}
      <SectionCard title="Platform">
        <div className="space-y-3 text-sm">
          {SERVICES.map((name, i) => (
            <div key={name} className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-0">
              <span className="text-muted-foreground">{name} version</span>
              <BuildValue name={name} build={builds[i].data} isPending={builds[i].isPending} isError={builds[i].isError} />
            </div>
          ))}
          {skew && (
            <p className="flex items-center gap-1.5 text-xs text-status-warning-fg" data-testid="build-skew">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              day1 and day2 run different versions.
            </p>
          )}
        </div>
      </SectionCard>
    </div>
  );
}
