import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

export function LoadingState({ label = "Loading records…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-ink/50">
      <Loader2 className="h-5 w-5 animate-spin" />
      <p className="font-mono text-xs uppercase tracking-wider">{label}</p>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-wire bg-paper/50 py-16 text-center">
      <Inbox className="h-6 w-6 text-ink/30" />
      <div>
        <p className="font-display text-lg text-ink">{title}</p>
        <p className="mx-auto mt-1 max-w-sm text-sm text-ink/55">{description}</p>
      </div>
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-rust/30 bg-rust/[0.04] py-16 text-center">
      <AlertTriangle className="h-6 w-6 text-rust" />
      <div>
        <p className="font-display text-lg text-ink">Couldn't load this</p>
        <p className="mx-auto mt-1 max-w-sm text-sm text-ink/60">{message}</p>
      </div>
      {onRetry && (
        <button className="btn-secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
