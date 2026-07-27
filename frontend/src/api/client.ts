/**
 * Thin API client. Access token lives only in memory (module-level
 * variable) — never localStorage — so it can't be read by injected
 * scripts or survive as a stealable artifact; the refresh token is an
 * HttpOnly cookie the browser handles on our behalf.
 */

let accessToken: string | null = null;
let csrfToken: string | null = null;

export function setTokens(access: string, csrf: string) {
  accessToken = access;
  csrfToken = csrf;
}

export function clearTokens() {
  accessToken = null;
  csrfToken = null;
}

async function refreshAccessToken(): Promise<boolean> {
  const res = await fetch("/api/auth/refresh", {
    method: "POST",
    credentials: "include",
    headers: csrfToken ? { "X-CSRF-Token": csrfToken } : {},
  });
  if (!res.ok) return false;
  const data = await res.json();
  setTokens(data.access_token, data.csrf_token);
  return true;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (!(init.body instanceof FormData) && init.body) headers.set("Content-Type", "application/json");

  let res = await fetch(`/api${path}`, { ...init, headers, credentials: "include" });

  if (res.status === 401 && path !== "/auth/login") {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      headers.set("Authorization", `Bearer ${accessToken}`);
      res = await fetch(`/api${path}`, { ...init, headers, credentials: "include" });
    }
  }
  return res;
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export function getCsrfToken() {
  return csrfToken;
}
