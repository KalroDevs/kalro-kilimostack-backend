import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-6 border-b border-wire px-8 py-6">
      <div>
        <p className="field-label">{eyebrow}</p>
        <h2 className="mt-1 font-display text-2xl font-semibold text-ink">{title}</h2>
        {description && <p className="mt-1.5 max-w-2xl text-sm text-ink/55">{description}</p>}
      </div>
      {actions && <div className="flex flex-shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
