import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { CheckCircle2, FileJson, Upload, XCircle } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { advisoryApi } from "@/lib/advisoryApi";
import type { IngestResult } from "@/types";

const PLACEHOLDER = `[
  {
    "title": "",
    "link": "",
    "publication_id": "",
    "institution": "Kenya Agricultural and Livestock Research Organization",
    "content_type": "",
    "language": "en",
    "sector": "",
    "value_chain": "",
    "commodity": [],
    "advisory_domain": [],
    "content": [],
    "advisory_safety": {}
  }
]`;

export function Import() {
  const [raw, setRaw] = useState("");
  const [parseError, setParseError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const ingestMutation = useMutation({
    mutationFn: (resources: unknown[]) => advisoryApi.ingest(resources),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resources"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
  });

  function handleFile(file: File) {
    const reader = new FileReader();
    reader.onload = () => setRaw(String(reader.result ?? ""));
    reader.readAsText(file);
  }

  function submit() {
    setParseError(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "Invalid JSON.");
      return;
    }
    const resources = Array.isArray(parsed) ? parsed : [parsed];
    ingestMutation.mutate(resources);
  }

  const result: IngestResult | undefined = ingestMutation.data;

  return (
    <>
      <PageHeader
        eyebrow="Advisory Content Import JSON Specification v0.1"
        title="Import resources"
        description="Paste or upload a JSON file matching the spec — a single object or an array of resources. Imports upsert by publication_id and land as unscreened until reviewed in the ledger."
      />

      <div className="grid grid-cols-1 gap-6 px-8 py-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="card">
            <div className="flex items-center justify-between border-b border-wire px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-medium text-ink/70">
                <FileJson className="h-4 w-4" /> resource.json
              </div>
              <button className="btn-ghost text-xs" onClick={() => fileInputRef.current?.click()}>
                <Upload className="h-3.5 w-3.5" /> Upload file
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/json"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
              />
            </div>
            <textarea
              className="h-96 w-full resize-none border-none bg-transparent p-4 font-mono text-xs text-ink outline-none placeholder:text-ink/30"
              placeholder={PLACEHOLDER}
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              spellCheck={false}
            />
          </div>

          {parseError && (
            <p className="mt-2 flex items-center gap-1.5 text-sm text-rust">
              <XCircle className="h-4 w-4" /> {parseError}
            </p>
          )}

          <div className="mt-4 flex items-center gap-3">
            <button className="btn-primary" onClick={submit} disabled={!raw.trim() || ingestMutation.isPending}>
              {ingestMutation.isPending ? "Importing…" : "Import"}
            </button>
            <button
              className="btn-ghost text-xs"
              onClick={() => {
                setRaw("");
                setParseError(null);
                ingestMutation.reset();
              }}
            >
              Clear
            </button>
          </div>

          {ingestMutation.isError && (
            <p className="mt-3 text-sm text-rust">
              Import failed — check that the Django backend is reachable (see Settings).
            </p>
          )}

          {result && (
            <div className="card mt-4 p-4">
              <h3 className="font-display text-base font-semibold text-ink">Import result</h3>
              <div className="mt-3 grid grid-cols-2 gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-herbarium" />
                  <span>{result.created.length} created</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-moss-dark" />
                  <span>{result.updated.length} updated</span>
                </div>
              </div>
              {result.errors.length > 0 && (
                <div className="mt-3 space-y-2">
                  {result.errors.map((err, i) => (
                    <div key={i} className="rounded-[3px] border border-rust/25 bg-rust/[0.04] p-2.5 text-xs">
                      <p className="font-mono font-semibold text-rust">{err.publication_id || "(no publication_id)"}</p>
                      <pre className="mt-1 whitespace-pre-wrap text-ink/60">{JSON.stringify(err.errors, null, 2)}</pre>
                    </div>
                  ))}
                </div>
              )}
              {(result.created.length > 0 || result.updated.length > 0) && (
                <Link to="/resources" className="mt-3 inline-block text-sm text-herbarium hover:underline">
                  Review imported resources in the ledger →
                </Link>
              )}
            </div>
          )}
        </div>

        <div className="card p-5">
          <h3 className="font-display text-base font-semibold text-ink">What's required</h3>
          <p className="mt-2 text-sm text-ink/60">
            Per the spec, every resource needs at minimum: <code className="font-mono text-xs">title</code>,{" "}
            <code className="font-mono text-xs">link</code>, <code className="font-mono text-xs">publication_id</code>,{" "}
            <code className="font-mono text-xs">institution</code>, <code className="font-mono text-xs">content_type</code>,{" "}
            <code className="font-mono text-xs">language</code>, <code className="font-mono text-xs">sector</code>,{" "}
            <code className="font-mono text-xs">value_chain</code>, and <code className="font-mono text-xs">commodity</code>.
          </p>
          <p className="mt-3 text-sm text-ink/60">
            Section-level content goes in the <code className="font-mono text-xs">content[]</code> array; risk
            information goes in <code className="font-mono text-xs">advisory_safety</code>.
          </p>
          <p className="mt-3 text-sm text-ink/60">
            Imported resources start <strong>unscreened</strong>. Nothing reaches the AI Layer until it's
            reviewed and marked <em>Ready to Certify</em> in the ledger.
          </p>
        </div>
      </div>
    </>
  );
}
