import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, XCircle } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { useSettingsStore } from "@/lib/settingsStore";
import { useAuthStore } from "@/lib/authStore";
import { advisoryApi } from "@/lib/advisoryApi";
import { aiLayerApi } from "@/lib/aiLayerApi";
import { humanize } from "@/lib/format";

export function Settings() {
  const store = useSettingsStore();
  const user = useAuthStore((s) => s.user);
  const [django, setDjango] = useState(store.djangoBaseUrl);
  const [aiLayer, setAiLayer] = useState(store.aiLayerBaseUrl);

  const djangoCheck = useQuery({
    queryKey: ["settings-django-check", store.djangoBaseUrl],
    queryFn: () => advisoryApi.listResources({}),
    retry: false,
  });
  const aiLayerCheck = useQuery({
    queryKey: ["settings-ai-check", store.aiLayerBaseUrl],
    queryFn: aiLayerApi.health,
    retry: false,
  });

  function save() {
    store.setDjangoBaseUrl(django);
    store.setAiLayerBaseUrl(aiLayer);
  }

  return (
    <>
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        description="Point this client at your running Django backend and FastAPI AI Layer. Stored locally in your browser."
      />

      <div className="mx-auto max-w-2xl space-y-6 px-8 py-6">
        {user && (
          <div className="card p-5">
            <h3 className="font-display text-base font-semibold text-ink">Session</h3>
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <dt className="text-ink/50">Logged in as</dt>
                <dd className="font-medium text-ink">{user.username}</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-ink/50">Provider access</dt>
                <dd className="text-right text-ink/80">
                  {user.provider_memberships.length > 0
                    ? user.provider_memberships.map((m) => `${m.provider_name} (${humanize(m.role)})`).join(", ")
                    : "None yet — ask an admin to link your account"}
                </dd>
              </div>
            </dl>
          </div>
        )}

        <div className="card p-5">
          <h3 className="font-display text-base font-semibold text-ink">Provider Platform (Django)</h3>
          <label className="mt-3 block">
            <span className="field-label">Base URL</span>
            <input className="input mt-1.5" value={django} onChange={(e) => setDjango(e.target.value)} placeholder="http://localhost:8000" />
          </label>
          <StatusRow
            checking={djangoCheck.isLoading}
            ok={djangoCheck.isSuccess}
            okLabel="Reachable"
            failLabel="Unreachable — check the URL and that the server is running"
          />
        </div>

        <div className="card p-5">
          <h3 className="font-display text-base font-semibold text-ink">AI Layer (FastAPI + Ollama)</h3>
          <label className="mt-3 block">
            <span className="field-label">Base URL</span>
            <input className="input mt-1.5" value={aiLayer} onChange={(e) => setAiLayer(e.target.value)} placeholder="http://localhost:8001" />
          </label>
          <StatusRow
            checking={aiLayerCheck.isLoading}
            ok={aiLayerCheck.isSuccess && aiLayerCheck.data?.status === "ok"}
            okLabel="Reachable, Ollama connected"
            failLabel="Unreachable, or Ollama isn't responding"
          />
        </div>

        <button className="btn-primary" onClick={save}>
          Save settings
        </button>
      </div>
    </>
  );
}

function StatusRow({
  checking,
  ok,
  okLabel,
  failLabel,
}: {
  checking: boolean;
  ok: boolean;
  okLabel: string;
  failLabel: string;
}) {
  return (
    <div className="mt-3 flex items-center gap-2 text-sm">
      {checking ? (
        <span className="text-ink/40">Checking…</span>
      ) : ok ? (
        <>
          <CheckCircle2 className="h-4 w-4 text-herbarium" />
          <span className="text-herbarium">{okLabel}</span>
        </>
      ) : (
        <>
          <XCircle className="h-4 w-4 text-rust" />
          <span className="text-rust">{failLabel}</span>
        </>
      )}
    </div>
  );
}
