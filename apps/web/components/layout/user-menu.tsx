"use client";

import { useRouter } from "next/navigation";
import { LogOut, Shield, Eye, ChevronDown, Sun, Moon } from "lucide-react";
import { useTheme } from "next-themes";
import { useAuthStore } from "@/stores/auth-store";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";

// Monday.com-style avatar color per initial
function avatarColor(initial: string) {
  const colors = [
    "bg-[#0073ea]",   // blue
    "bg-[#00c875]",   // green
    "bg-[#9b51e0]",   // purple
    "bg-[#ff7575]",   // coral
    "bg-[#fdab3d]",   // orange
    "bg-[#33d391]",   // teal
    "bg-[#e2445c]",   // red
    "bg-[#579bfc]",   // light blue
  ];
  return colors[(initial.charCodeAt(0) - 65) % colors.length];
}

export function UserMenu() {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const { theme, setTheme } = useTheme();

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  if (!user) return null;

  const initial = user.username.charAt(0).toUpperCase();
  const bgColor = avatarColor(initial);
  const isDark = theme === "dark";

  return (
    <Popover>
      <PopoverTrigger className="inline-flex items-center gap-2 rounded-lg px-2 h-8 hover:bg-muted transition-colors">
        <div className={`flex h-7 w-7 items-center justify-center rounded-full text-white text-xs font-bold ${bgColor}`}>
          {initial}
        </div>
        <span className="hidden sm:inline text-sm font-medium">{user.username}</span>
        <ChevronDown className="hidden sm:block h-3.5 w-3.5 text-muted-foreground" />
      </PopoverTrigger>
      <PopoverContent align="end" className="w-60 p-2 shadow-lg">
        {/* User info */}
        <div className="px-2 py-2">
          <div className="flex items-center gap-2.5">
            <div className={`flex h-9 w-9 items-center justify-center rounded-full text-white text-sm font-bold ${bgColor}`}>
              {initial}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold truncate">{user.username}</p>
              {user.role === "admin" ? (
                <span className="inline-flex items-center gap-1 text-xs text-primary font-medium">
                  <Shield className="h-3 w-3" />Admin
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <Eye className="h-3 w-3" />Viewer
                </span>
              )}
            </div>
          </div>
          {user.groups && user.groups.length > 0 && (
            <p className="text-xs text-muted-foreground truncate mt-1.5 pl-0.5">
              {user.groups.slice(0, 2).join(", ")}
              {user.groups.length > 2 && ` +${user.groups.length - 2}`}
            </p>
          )}
        </div>

        <Separator className="my-1.5" />

        {/* Theme toggle */}
        <div className="flex items-center justify-between px-2 py-1.5 rounded-md">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            {isDark ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
            <span>{isDark ? "Dark" : "Light"} mode</span>
          </div>
          <button
            onClick={() => setTheme(isDark ? "light" : "dark")}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
              isDark ? "bg-primary" : "bg-muted-foreground/30"
            }`}
            role="switch"
            aria-checked={isDark}
          >
            <span
              className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                isDark ? "translate-x-4" : "translate-x-0.5"
              }`}
            />
          </button>
        </div>

        <Separator className="my-1.5" />

        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </PopoverContent>
    </Popover>
  );
}
