import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowUpRight, FlaskConical } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { LoadingState, ErrorState } from "@/components/States";
import { advisoryApi } from "@/lib/advisoryApi";
import { aiLayerApi } from "@/lib/aiLayerApi";
import { humanize } from "@/lib/format";

const QUALITY_FLAGS = ["ready_to_certify", "needs_review", "needs_update", "duplicate", "reject"] as const;
const SECTORS = ["crops", "livestock", "aquaculture", "natural_resource_management", "cross_cutting"] as const;

export function Dashboard() {
  const overview = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: async () => {
      const [total, ...qualityCounts] = await Promise.all([
        advisoryApi.listResources({}),
        ...QUALITY_FLAGS.map((qf) => advisoryApi.listResources({ quality_flag: qf })),
      ]);
      const sectorCounts = await Promise.all(
        SECTORS.map((s) => advisoryApi.listResources({ sector: s }))
      );
      return {
        total: total.count,
        byQuality: QUALITY_FLAGS.map((qf, i) => ({ key: qf, count: qualityCounts[i].count })),
        bySector: SECTORS.map((s, i) => ({ key: s, count: sectorCounts[i].count })),
        recent: total.results.slice(0, 6),
      };
    },
  });

  const aiHealth = useQuery({
    queryKey: ["ai-layer-health"],
    queryFn: aiLayerApi.health,
    retry: false,
  });

  return (
    <>
      <PageHeader
        eyebrow="Field Overview"
        title="The corpus at a glance"
        description="What's certified, what's waiting on review, and whether the AI Layer is reachable."
      />

      <div className="px-8 py-6">
        {overview.isLoading && <LoadingState label="Tallying the ledger…" />}
        {overview.isError && (
          <ErrorState
            message="Couldn't reach the Django backend. Check the API URL under Settings."
            onRetry={() => overview.refetch()}
          />
        )}

        {overview.data && (
          <div className="space-y-8">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Total resources" value={overview.data.total} />
              <StatCard
                label="Ready to certify"
                value={overview.data.byQuality.find((q) => q.key === "ready_to_certify")?.count ?? 0}
                tone="herbarium"
              />
              <StatCard
                label="Needs review"
                value={overview.data.byQuality.find((q) => q.key === "needs_review")?.count ?? 0}
                tone="ochre"
              />
              <StatCard
                label="Flagged / rejected"
                value={overview.data.byQuality.find((q) => q.key === "reject")?.count ?? 0}
                tone="rust"
              />
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              <div className="card p-5 lg:col-span-2">
                <h3 className="font-display text-base font-semibold text-ink">By sector</h3>
                <div className="mt-4 space-y-3">
                  {overview.data.bySector.map(({ key, count }) => (
                    <BarRow
                      key={key}
                      label={humanize(key)}
                      value={count}
                      max={Math.max(...overview.data.bySector.map((s) => s.count), 1)}
                    />
                  ))}
                </div>
              </div>

              <div className="card p-5">
                <div className="flex items-center gap-2">
                  <FlaskConical className="h-4 w-4 text-herbarium" />
                  <h3 className="font-display text-base font-semibold text-ink">AI Layer</h3>
                </div>
                {aiHealth.isLoading && <p className="mt-3 text-sm text-ink/50">Checking…</p>}
                {aiHealth.isError && (
                  <p className="mt-3 text-sm text-rust">
                    Unreachable. Confirm the AI Layer URL under Settings and that Ollama is running.
                  </p>
                )}
                {aiHealth.data && (
                  <div className="mt-3 space-y-2 text-sm">
                    <Row label="Status" value={aiHealth.data.status === "ok" ? "Reachable" : "Degraded"} />
                    <Row label="Chat model" value={aiHealth.data.models.chat} mono />
                    <Row label="Embed model" value={aiHealth.data.models.embed} mono />
                    <Row label="Indexed chunks" value={String(aiHealth.data.vector_store.indexed_chunks)} />
                  </div>
                )}
              </div>
            </div>

            <div className="card p-5">
              <div className="flex items-center justify-between">
                <h3 className="font-display text-base font-semibold text-ink">Recently updated</h3>
                <Link to="/resources" className="inline-flex items-center gap-1 text-sm text-herbarium hover:underline">
                  View full ledger <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
              </div>
              <ul className="mt-3 divide-y divide-wire">
                {overview.data.recent.map((r) => (
                  <li key={r.id}>
                    <Link
                      to={`/resources/${r.id}`}
                      className="flex items-center justify-between gap-4 py-2.5 text-sm hover:text-herbarium"
                    >
                      <span className="truncate">{r.title}</span>
                      <span className="flex-shrink-0 font-mono text-xs text-ink/40">{r.publication_id}</span>
                    </Link>
                  </li>
                ))}
                {overview.data.recent.length === 0 && (
                  <li className="py-4 text-sm text-ink/45">Nothing imported yet.</li>
                )}
              </ul>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function StatCard({ label, value, tone }: { label: string; value: number; tone?: "herbarium" | "ochre" | "rust" }) {
  const toneColor = tone === "herbarium" ? "text-herbarium" : tone === "ochre" ? "text-ochre-dark" : tone === "rust" ? "text-rust" : "text-ink";
  return (
    <div className="card p-5">
      <p className="field-label">{label}</p>
      <p className={`mt-2 font-display text-3xl font-semibold ${toneColor}`}>{value}</p>
    </div>
  );
}

function BarRow({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.max((value / max) * 100, value > 0 ? 3 : 0);
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="text-ink/75">{label}</span>
        <span className="font-mono text-xs text-ink/50">{value}</span>
      </div>
      <div className="mt-1 h-1.5 w-full rounded-full bg-canvas2">
        <div className="h-1.5 rounded-full bg-moss" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-ink/50">{label}</span>
      <span className={mono ? "font-mono text-xs text-ink/80" : "text-ink/80"}>{value}</span>
    </div>
  );
}
