import { create } from "zustand";
import { apiJson, setTokens, clearTokens } from "../api/client";

interface AuthState {
  isAuthenticated: boolean;
  setupRequired: boolean | null;
  username: string | null;
  checkSetup: () => Promise<void>;
  setupAdmin: (username: string, password: string) => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: false,
  setupRequired: null,
  username: null,

  checkSetup: async () => {
    const data = await apiJson<{ setup_required: boolean }>("/auth/setup-required");
    set({ setupRequired: data.setup_required });
  },

  setupAdmin: async (username, password) => {
    await apiJson("/auth/setup", { method: "POST", body: JSON.stringify({ username, password }) });
    set({ setupRequired: false });
  },

  login: async (username, password) => {
    const data = await apiJson<{ access_token: string; csrf_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setTokens(data.access_token, data.csrf_token);
    set({ isAuthenticated: true, username });
  },

  logout: async () => {
    await apiJson("/auth/logout", { method: "POST" }).catch(() => {});
    clearTokens();
    set({ isAuthenticated: false, username: null });
  },
}));
