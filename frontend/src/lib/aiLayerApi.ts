import { useSettingsStore } from "./settingsStore";
import type { AiLayerHealth, ChatRequest, ChatResponse } from "@/types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { aiLayerBaseUrl } = useSettingsStore.getState();
  const res = await fetch(`${aiLayerBaseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers as Record<string, string>) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`AI Layer request to ${path} failed (${res.status}): ${text}`);
  }
  return (await res.json()) as T;
}

export const aiLayerApi = {
  health: () => request<AiLayerHealth>("/health"),
  chat: (payload: ChatRequest) =>
    request<ChatResponse>("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
