import { useSettingsStore } from "./settingsStore";
import type { AuthResponse, CurrentUser, LoginPayload, RegisterPayload } from "@/types";

class AuthApiError extends Error {
  status: number;
  fieldErrors: Record<string, string[]> | null;
  constructor(message: string, status: number, fieldErrors: Record<string, string[]> | null) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

async function request<T>(path: string, init?: RequestInit, token?: string): Promise<T> {
  const { djangoBaseUrl } = useSettingsStore.getState();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Token ${token}`;

  const res = await fetch(`${djangoBaseUrl}${path}`, { ...init, headers });

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* ignore non-JSON error body */
    }
    const isFieldErrors = body && typeof body === "object" && !("detail" in (body as object));
    const message =
      (body as { detail?: string })?.detail ??
      (isFieldErrors ? "Please check the highlighted fields." : `Request failed (${res.status})`);
    throw new AuthApiError(message, res.status, isFieldErrors ? (body as Record<string, string[]>) : null);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const authApi = {
  register: (payload: RegisterPayload) =>
    request<AuthResponse>("/api/v1/auth/register/", { method: "POST", body: JSON.stringify(payload) }),

  login: (payload: LoginPayload) =>
    request<AuthResponse>("/api/v1/auth/login/", { method: "POST", body: JSON.stringify(payload) }),

  me: (token: string) => request<CurrentUser>("/api/v1/auth/me/", { method: "GET" }, token),

  logout: (token: string) => request<void>("/api/v1/auth/logout/", { method: "POST" }, token),
};

export { AuthApiError };
