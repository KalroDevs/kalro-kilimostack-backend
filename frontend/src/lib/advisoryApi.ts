import { useSettingsStore } from "./settingsStore";
import { useAuthStore } from "./authStore";
import type {
  AdvisoryResource,
  IngestResult,
  PaginatedResponse,
  ResourceFilters,
  ScreeningUpdate,
} from "@/types";

class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { djangoBaseUrl } = useSettingsStore.getState();
  const { token } = useAuthStore.getState();
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
      /* non-JSON error body, ignore */
    }
    throw new ApiError(`Request to ${path} failed (${res.status})`, res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function buildQuery(filters: ResourceFilters = {}): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  });
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export const advisoryApi = {
  listResources: (filters: ResourceFilters = {}) =>
    request<PaginatedResponse<AdvisoryResource>>(`/api/v1/resources/${buildQuery(filters)}`),

  getResource: (id: number) => request<AdvisoryResource>(`/api/v1/resources/${id}/`),

  updateScreening: (id: number, data: ScreeningUpdate) =>
    request<AdvisoryResource>(`/api/v1/resources/${id}/screen/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  syncToAiLayer: (id: number) =>
    request<{ publication_id: string; vector_sync_status: string; vector_sync_error: string }>(
      `/api/v1/resources/${id}/sync-to-ai-layer/`,
      { method: "POST" }
    ),

  syncAllReady: () =>
    request<{ synced: number; skipped: number; failed: number }>(`/api/v1/resources/sync-ready/`, {
      method: "POST",
    }),

  ingest: (resources: unknown[]) =>
    request<IngestResult>(`/api/v1/ingest/`, {
      method: "POST",
      body: JSON.stringify(resources),
    }),

  deleteResource: (id: number) =>
    request<void>(`/api/v1/resources/${id}/`, { method: "DELETE" }),
};

export { ApiError };
