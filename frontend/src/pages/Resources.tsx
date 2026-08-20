import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { LoadingState, ErrorState, EmptyState } from "@/components/States";
import { QualityFlagStamp, RiskLevelStamp } from "@/components/Stamp";
import { SectorChip } from "@/components/SectorChip";
import { advisoryApi } from "@/lib/advisoryApi";
import { formatDate } from "@/lib/format";
import type { ResourceFilters } from "@/types";

const SECTOR_OPTIONS = ["crops", "livestock", "aquaculture", "natural_resource_management", "cross_cutting"];
const QUALITY_OPTIONS = ["ready_to_certify", "needs_review", "needs_update", "duplicate", "reject"];
const RISK_OPTIONS = ["low", "medium", "high"];

export function Resources() {
  const [filters, setFilters] = useState<ResourceFilters>({});
  const [searchInput, setSearchInput] = useState("");

  const query = useQuery({
    queryKey: ["resources", filters],
    queryFn: () => advisoryApi.listResources(filters),
  });

  function updateFilter<K extends keyof ResourceFilters>(key: K, value: ResourceFilters[K]) {
    setFilters((prev) => ({ ...prev, [key]: value || undefined, page: undefined }));
  }

  return (
    <>
      <PageHeader
        eyebrow="Screen & Classify"
        title="Corpus ledger"
        description="Sort by crop, topic and content type, then screen each item for scientific accuracy and currency before it's certified."
        actions={
          <Link to="/import" className="btn-primary">
            Import resources
          </Link>
        }
      />

      <div className="border-b border-wire bg-paper/60 px-8 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <form
            className="relative w-64"
            onSubmit={(e) => {
              e.preventDefault();
              updateFilter("search", searchInput);
            }}
          >
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink/35" />
            <input
              className="input pl-8"
              placeholder="Search title, ID, value chain…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </form>

          <FilterSelect
            label="Sector"
            value={filters.sector ?? ""}
            options={SECTOR_OPTIONS}
            onChange={(v) => updateFilter("sector", v)}
          />
          <FilterSelect
            label="Quality flag"
            value={filters.quality_flag ?? ""}
            options={QUALITY_OPTIONS}
            onChange={(v) => updateFilter("quality_flag", v)}
          />
          <FilterSelect
            label="Risk level"
            value={filters.risk_level ?? ""}
            options={RISK_OPTIONS}
            onChange={(v) => updateFilter("risk_level", v)}
          />

          {(filters.sector || filters.quality_flag || filters.risk_level || filters.search) && (
            <button
              className="btn-ghost text-xs"
              onClick={() => {
                setFilters({});
                setSearchInput("");
              }}
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      <div className="px-8 py-6">
        {query.isLoading && <LoadingState label="Reading the ledger…" />}
        {query.isError && (
          <ErrorState message="Couldn't reach the Django backend. Check the API URL under Settings." onRetry={() => query.refetch()} />
        )}

        {query.data && query.data.results.length === 0 && (
          <EmptyState
            title="No matching resources"
            description="Nothing in the corpus matches these filters yet. Import a resource to get started."
            action={
              <Link to="/import" className="btn-primary">
                Import resources
              </Link>
            }
          />
        )}

        {query.data && query.data.results.length > 0 && (
          <div className="card overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-wire bg-canvas2/60 text-xs text-ink/50">
                  <th className="px-4 py-3 font-mono font-medium uppercase tracking-wider">ID</th>
                  <th className="px-4 py-3 font-mono font-medium uppercase tracking-wider">Title</th>
                  <th className="px-4 py-3 font-mono font-medium uppercase tracking-wider">Sector</th>
                  <th className="px-4 py-3 font-mono font-medium uppercase tracking-wider">Value chain</th>
                  <th className="px-4 py-3 font-mono font-medium uppercase tracking-wider">Quality</th>
                  <th className="px-4 py-3 font-mono font-medium uppercase tracking-wider">Risk</th>
                  <th className="px-4 py-3 font-mono font-medium uppercase tracking-wider">Updated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-wire">
                {query.data.results.map((r) => (
                  <tr key={r.id} className="hover:bg-canvas2/40">
                    <td className="px-4 py-3">
                      <Link to={`/resources/${r.id}`} className="font-mono text-xs text-herbarium hover:underline">
                        {r.publication_id}
                      </Link>
                    </td>
                    <td className="max-w-xs px-4 py-3">
                      <Link to={`/resources/${r.id}`} className="line-clamp-1 text-ink hover:text-herbarium">
                        {r.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <SectorChip sector={r.sector} />
                    </td>
                    <td className="px-4 py-3 text-ink/70">{r.value_chain || "—"}</td>
                    <td className="px-4 py-3">
                      <QualityFlagStamp value={r.quality_flag} />
                    </td>
                    <td className="px-4 py-3">
                      <RiskLevelStamp value={r.advisory_safety?.risk_level ?? ""} />
                    </td>
                    <td className="px-4 py-3 text-xs text-ink/50">{formatDate(r.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {query.data && (
          <div className="mt-4 flex items-center justify-between text-xs text-ink/45">
            <span>{query.data.count} resource(s) total</span>
            <div className="flex gap-2">
              <button
                className="btn-secondary px-2.5 py-1 text-xs"
                disabled={!query.data.previous}
                onClick={() => setFilters((prev) => ({ ...prev, page: (prev.page ?? 1) - 1 }))}
              >
                Previous
              </button>
              <button
                className="btn-secondary px-2.5 py-1 text-xs"
                disabled={!query.data.next}
                onClick={() => setFilters((prev) => ({ ...prev, page: (prev.page ?? 1) + 1 }))}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <select
      className="select w-auto min-w-[10rem] text-sm"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={label}
    >
      <option value="">{label}: All</option>
      {options.map((opt) => (
        <option key={opt} value={opt}>
          {opt.replace(/_/g, " ")}
        </option>
      ))}
    </select>
  );
}
