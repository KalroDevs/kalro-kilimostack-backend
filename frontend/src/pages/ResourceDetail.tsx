import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, RefreshCw, ShieldAlert } from "lucide-react";
import { LoadingState, ErrorState } from "@/components/States";
import { QualityFlagStamp, RiskLevelStamp } from "@/components/Stamp";
import { SectorChip } from "@/components/SectorChip";
import { advisoryApi, ApiError } from "@/lib/advisoryApi";
import { formatDate, formatDateTime, humanize } from "@/lib/format";
import type { ScreeningUpdate } from "@/types";

export function ResourceDetail() {
  const { id } = useParams<{ id: string }>();
  const resourceId = Number(id);
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["resource", resourceId],
    queryFn: () => advisoryApi.getResource(resourceId),
    enabled: Number.isFinite(resourceId),
  });

  const [form, setForm] = useState<ScreeningUpdate>({});
  useEffect(() => {
    if (query.data) {
      setForm({
        currency_status: query.data.currency_status,
        scientific_accuracy_check: query.data.scientific_accuracy_check,
        validation_status: query.data.validation_status,
        risk_level: query.data.advisory_safety?.risk_level,
        quality_flag: query.data.quality_flag,
        screening_notes: query.data.screening_notes,
      });
    }
  }, [query.data]);

  const screenMutation = useMutation({
    mutationFn: (data: ScreeningUpdate) => advisoryApi.updateScreening(resourceId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resource", resourceId] });
      queryClient.invalidateQueries({ queryKey: ["resources"] });
    },
  });

  const syncMutation = useMutation({
    mutationFn: () => advisoryApi.syncToAiLayer(resourceId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["resource", resourceId] }),
  });

  if (query.isLoading) return <LoadingState label="Retrieving record…" />;
  if (query.isError || !query.data)
    return (
      <div className="px-8 py-6">
        <ErrorState
          message="Couldn't load this resource. It may not exist, or the backend is unreachable."
          onRetry={() => query.refetch()}
        />
      </div>
    );

  const r = query.data;

  return (
    <>
      <div className="border-b border-wire px-8 py-6">
        <Link to="/resources" className="inline-flex items-center gap-1.5 text-xs font-medium text-ink/50 hover:text-herbarium">
          <ArrowLeft className="h-3.5 w-3.5" /> Corpus ledger
        </Link>
        <div className="mt-3 flex items-start justify-between gap-6">
          <div>
            <p className="field-label">{r.publication_id}</p>
            <h2 className="mt-1 font-display text-2xl font-semibold text-ink">{r.title}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-ink/55">
              <SectorChip sector={r.sector} />
              <span>·</span>
              <span>{r.value_chain || "No value chain set"}</span>
              <span>·</span>
              <span>{humanize(r.content_type)}</span>
              {r.link && (
                <a href={r.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-herbarium hover:underline">
                  Source <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          </div>
          <div className="flex flex-shrink-0 flex-col items-end gap-2">
            <QualityFlagStamp value={r.quality_flag} />
            <RiskLevelStamp value={r.advisory_safety?.risk_level ?? ""} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 px-8 py-6 lg:grid-cols-3">
        {/* Left: content sections */}
        <div className="space-y-4 lg:col-span-2">
          <div className="card p-5">
            <h3 className="font-display text-base font-semibold text-ink">Resource metadata</h3>
            <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2.5 text-sm">
              <MetaRow label="Institution" value={r.institution} />
              <MetaRow label="Author(s)" value={r.author.join(", ") || "—"} />
              <MetaRow label="Published" value={r.publish_date || "—"} />
              <MetaRow label="Last modified" value={formatDate(r.modified_date)} />
              <MetaRow label="Language" value={r.language} />
              <MetaRow label="Commodity" value={r.commodity.join(", ") || "—"} />
              <MetaRow label="Advisory domain" value={r.advisory_domain.join(", ") || "—"} />
              <MetaRow label="Target users" value={r.target_users.join(", ") || "—"} />
              <MetaRow
                label="Country / AEZ"
                value={[r.geographic_applicability?.country, ...(r.geographic_applicability?.agro_ecological_zones ?? [])]
                  .filter(Boolean)
                  .join(", ")}
              />
              <MetaRow label="Validation status" value={humanize(r.validation_status)} />
            </dl>
          </div>

          {r.advisory_safety?.escalation_guidance && (
            <div className="card border-rust/30 bg-rust/[0.03] p-5">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-rust" />
                <h3 className="font-display text-base font-semibold text-ink">Advisory safety</h3>
              </div>
              <p className="mt-2 text-sm text-ink/70">{r.advisory_safety.escalation_guidance}</p>
              {r.advisory_safety.risk_domains?.length > 0 && (
                <p className="mt-2 text-xs text-ink/50">Risk domains: {r.advisory_safety.risk_domains.join(", ")}</p>
              )}
            </div>
          )}

          <div className="card p-5">
            <h3 className="font-display text-base font-semibold text-ink">
              Content sections <span className="font-mono text-xs font-normal text-ink/40">({r.content.length})</span>
            </h3>
            <div className="mt-3 space-y-3">
              {r.content
                .slice()
                .sort((a, b) => a.reading_order - b.reading_order)
                .map((section) => (
                  <details key={section.content_id} className="rounded-[3px] border border-wire bg-canvas/40 open:bg-canvas/60">
                    <summary className="flex cursor-pointer items-center justify-between px-3.5 py-2.5 text-sm font-medium text-ink">
                      <span>
                        {section.reading_order}. {section.content_header || "Untitled section"}
                      </span>
                      {section.content_warnings.length > 0 && (
                        <span className="flex-shrink-0 text-xs text-rust">⚠ {section.content_warnings.length} warning(s)</span>
                      )}
                    </summary>
                    <div className="border-t border-wire px-3.5 py-3 text-sm">
                      <p className="text-ink/75">{section.content_text}</p>
                      {section.content_warnings.length > 0 && (
                        <div className="mt-3 space-y-1 rounded-[3px] border border-rust/25 bg-rust/[0.04] p-2.5">
                          {section.content_warnings.map((w, i) => (
                            <p key={i} className="text-xs text-rust">
                              {w}
                            </p>
                          ))}
                        </div>
                      )}
                      {section.content_tags.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {section.content_tags.map((tag) => (
                            <span key={tag} className="rounded-full bg-canvas2 px-2 py-0.5 text-xs text-ink/55">
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </details>
                ))}
              {r.content.length === 0 && <p className="text-sm text-ink/45">No content sections recorded.</p>}
            </div>
          </div>
        </div>

        {/* Right: screening form + sync */}
        <div className="space-y-4">
          <div className="card p-5">
            <h3 className="font-display text-base font-semibold text-ink">Screen &amp; classify</h3>
            <p className="mt-1 text-xs text-ink/50">
              Check scientific accuracy and currency, then set the quality flag that decides whether this
              reaches the AI Layer.
            </p>

            <form
              className="mt-4 space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                screenMutation.mutate(form);
              }}
            >
              <Field label="Currency status">
                <select
                  className="select"
                  value={form.currency_status ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, currency_status: e.target.value as ScreeningUpdate["currency_status"] }))}
                >
                  <option value="">Not set</option>
                  <option value="current">Current</option>
                  <option value="needs_update">Needs update</option>
                  <option value="outdated">Outdated</option>
                  <option value="needs_verification">Needs verification</option>
                </select>
              </Field>

              <Field label="Scientific accuracy check">
                <select
                  className="select"
                  value={form.scientific_accuracy_check ?? ""}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, scientific_accuracy_check: e.target.value as ScreeningUpdate["scientific_accuracy_check"] }))
                  }
                >
                  <option value="">Not set</option>
                  <option value="verified">Verified</option>
                  <option value="needs_review">Needs review</option>
                  <option value="flagged_inaccurate">Flagged — inaccurate</option>
                </select>
              </Field>

              <Field label="Validation status">
                <select
                  className="select"
                  value={form.validation_status ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, validation_status: e.target.value as ScreeningUpdate["validation_status"] }))}
                >
                  <option value="">Not set</option>
                  <option value="source_validated">Source validated</option>
                  <option value="expert_reviewed">Expert reviewed</option>
                  <option value="field_validated">Field validated</option>
                  <option value="requires_review">Requires review</option>
                  <option value="deprecated">Deprecated</option>
                </select>
              </Field>

              <Field label="Risk level">
                <select
                  className="select"
                  value={form.risk_level ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, risk_level: e.target.value as ScreeningUpdate["risk_level"] }))}
                >
                  <option value="">Not set</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </Field>

              <Field label="Quality flag">
                <select
                  className="select"
                  value={form.quality_flag ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, quality_flag: e.target.value as ScreeningUpdate["quality_flag"] }))}
                >
                  <option value="">Unscreened</option>
                  <option value="ready_to_certify">Ready to certify</option>
                  <option value="needs_review">Needs review</option>
                  <option value="needs_update">Needs update</option>
                  <option value="duplicate">Duplicate</option>
                  <option value="reject">Reject</option>
                </select>
              </Field>

              <Field label="Screening notes">
                <textarea
                  className="textarea"
                  rows={4}
                  placeholder="Reviewer notes, open questions, escalation contacts…"
                  value={form.screening_notes ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, screening_notes: e.target.value }))}
                />
              </Field>

              <button type="submit" className="btn-primary w-full" disabled={screenMutation.isPending}>
                {screenMutation.isPending ? "Saving…" : "Save screening decision"}
              </button>
              {screenMutation.isSuccess && <p className="text-center text-xs text-herbarium">Saved.</p>}
              {screenMutation.isError && (
                <p className="text-center text-xs text-rust">
                  {screenMutation.error instanceof ApiError && screenMutation.error.status === 401
                    ? "Sign-in required — add an auth token under Settings to save screening decisions."
                    : "Couldn't save — check the connection and try again."}
                </p>
              )}
            </form>
          </div>

          <div className="card p-5">
            <h3 className="font-display text-base font-semibold text-ink">AI Layer sync</h3>
            <dl className="mt-3 space-y-2 text-sm">
              <MetaRow label="Status" value={humanize(r.vector_sync_status)} />
              <MetaRow label="Last synced" value={formatDateTime(r.vector_synced_at)} />
            </dl>
            <button
              className="btn-secondary mt-3 w-full"
              onClick={() => syncMutation.mutate()}
              disabled={syncMutation.isPending || r.quality_flag !== "ready_to_certify"}
              title={r.quality_flag !== "ready_to_certify" ? "Mark as Ready to Certify first" : undefined}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${syncMutation.isPending ? "animate-spin" : ""}`} />
              {syncMutation.isPending ? "Syncing…" : "Sync to AI Layer"}
            </button>
            {r.quality_flag !== "ready_to_certify" && (
              <p className="mt-2 text-xs text-ink/45">Only certified resources are indexed for the RAG service.</p>
            )}
            {syncMutation.isError && <p className="mt-2 text-xs text-rust">Sync failed — the AI Layer may be unreachable.</p>}
          </div>
        </div>
      </div>
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="field-label">{label}</dt>
      <dd className="mt-0.5 text-ink/80">{value || "—"}</dd>
    </div>
  );
}
