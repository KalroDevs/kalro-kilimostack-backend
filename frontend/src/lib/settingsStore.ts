import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SettingsState {
  djangoBaseUrl: string;
  aiLayerBaseUrl: string;
  setDjangoBaseUrl: (url: string) => void;
  setAiLayerBaseUrl: (url: string) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      djangoBaseUrl: "http://localhost:8000",
      aiLayerBaseUrl: "http://localhost:8001",
      setDjangoBaseUrl: (url) => set({ djangoBaseUrl: url.replace(/\/$/, "") }),
      setAiLayerBaseUrl: (url) => set({ aiLayerBaseUrl: url.replace(/\/$/, "") }),
    }),
    { name: "kilimostack-settings" }
  )
);
