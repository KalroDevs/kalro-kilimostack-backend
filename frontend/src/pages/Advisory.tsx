import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, ArrowUp, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { aiLayerApi } from "@/lib/aiLayerApi";
import type { ChatResponse } from "@/types";

interface Turn {
  query: string;
  response?: ChatResponse;
  error?: string;
}

const SECTOR_OPTIONS = ["", "crops", "livestock", "aquaculture", "natural_resource_management", "cross_cutting"];

const SAMPLE_QUESTIONS = [
  "How do I manage tick paralysis in camel calves?",
  "When should I wean a camel calf?",
  "What should I do if a newborn calf isn't breathing?",
];

export function Advisory() {
  const [input, setInput] = useState("");
  const [sector, setSector] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);

  const chatMutation = useMutation({
    mutationFn: (query: string) =>
      aiLayerApi.chat({ query, filters: sector ? { sector } : undefined }),
  });

  function ask(query: string) {
    if (!query.trim()) return;
    setTurns((prev) => [...prev, { query }]);
    setInput("");
    chatMutation.mutate(query, {
      onSuccess: (response) => {
        setTurns((prev) => prev.map((t, i) => (i === prev.length - 1 ? { ...t, response } : t)));
      },
      onError: (err) => {
        setTurns((prev) =>
          prev.map((t, i) => (i === prev.length - 1 ? { ...t, error: err instanceof Error ? err.message : "Request failed" } : t))
        );
      },
    });
  }

  return (
    <>
      <PageHeader
        eyebrow="RAG + Ollama"
        title="Ask the advisory AI"
        description="Queries the AI Layer directly — answers are grounded only in certified KALRO content that has been synced to the vector index."
        actions={
          <select className="select w-auto text-sm" value={sector} onChange={(e) => setSector(e.target.value)}>
            {SECTOR_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s ? `Filter: ${s.replace(/_/g, " ")}` : "All sectors"}
              </option>
            ))}
          </select>
        }
      />

      <div className="mx-auto flex h-[calc(100vh-6.5rem)] max-w-3xl flex-col px-8 py-6">
        <div className="flex-1 space-y-6 overflow-y-auto pb-4">
          {turns.length === 0 && (
            <div className="rounded-md border border-dashed border-wire bg-paper/50 p-6">
              <div className="flex items-center gap-2 text-ink/70">
                <Sparkles className="h-4 w-4 text-ochre-dark" />
                <p className="font-display text-base font-semibold">Try a question</p>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {SAMPLE_QUESTIONS.map((q) => (
                  <button key={q} className="btn-secondary text-xs" onClick={() => ask(q)}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn, i) => (
            <div key={i} className="space-y-3">
              <div className="ml-auto max-w-[85%] rounded-md rounded-tr-none bg-herbarium px-4 py-2.5 text-sm text-paper">
                {turn.query}
              </div>

              {!turn.response && !turn.error && (
                <div className="max-w-[85%] rounded-md rounded-tl-none border border-wire bg-paper px-4 py-2.5 text-sm text-ink/50">
                  Retrieving grounded context and generating a response…
                </div>
              )}

              {turn.error && (
                <div className="flex max-w-[85%] items-start gap-2 rounded-md rounded-tl-none border border-rust/30 bg-rust/[0.04] px-4 py-2.5 text-sm text-rust">
                  <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                  <span>Couldn't reach the AI Layer. Check the API URL under Settings and confirm Ollama is running.</span>
                </div>
              )}

              {turn.response && (
                <div className="max-w-[85%] space-y-3 rounded-md rounded-tl-none border border-wire bg-paper px-4 py-3.5 text-sm text-ink">
                  <p className="whitespace-pre-wrap leading-relaxed">{turn.response.answer}</p>

                  {turn.response.safety_notice && (
                    <div className="flex items-start gap-2 rounded-[3px] border border-ochre/30 bg-ochre/[0.08] px-3 py-2 text-xs text-ochre-dark">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                      <span>{turn.response.safety_notice}</span>
                    </div>
                  )}

                  {turn.response.sources.length > 0 && (
                    <div className="border-t border-wire pt-2.5">
                      <p className="field-label mb-1.5">Sources</p>
                      <ul className="space-y-1">
                        {turn.response.sources.map((s, si) => (
                          <li key={si} className="flex items-center justify-between gap-3 text-xs">
                            <span className="truncate text-ink/70">
                              {s.title} — <span className="text-ink/45">{s.content_header}</span>
                            </span>
                            <span className="flex-shrink-0 font-mono text-ink/35">{s.score.toFixed(2)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <p className="font-mono text-[10px] uppercase tracking-wider text-ink/30">{turn.response.model}</p>
                </div>
              )}
            </div>
          ))}
        </div>

        <form
          className="flex items-center gap-2 border-t border-wire pt-4"
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
        >
          <input
            className="input flex-1"
            placeholder="Ask about a crop, livestock issue, or advisory topic…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button type="submit" className="btn-primary" disabled={!input.trim() || chatMutation.isPending}>
            <ArrowUp className="h-4 w-4" />
          </button>
        </form>
      </div>
    </>
  );
}
