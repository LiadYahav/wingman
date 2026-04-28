"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { clearToken, setToken } from "@/lib/api-client";

export interface AuthUser {
  username: string;
  groups: string[];
  uid: string;
  full_name?: string;
  role: "admin" | "viewer";
}

interface AuthState {
  user: AuthUser | null;
  isAuthenticated: boolean;
  login: (token: string, user: AuthUser) => void;
  logout: () => void;
}

export function useIsAdmin(): boolean {
  return useAuthStore((s) => s.user?.role === "admin");
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,

      login: (token: string, user: AuthUser) => {
        setToken(token);
        set({ user, isAuthenticated: true });
      },

      logout: () => {
        clearToken();
        set({ user: null, isAuthenticated: false });
      },
    }),
    {
      name: "wingman-auth",
      // Only persist user info — token is in the cookie
      partialize: (state) => ({ user: state.user, isAuthenticated: state.isAuthenticated }),
    }
  )
);
