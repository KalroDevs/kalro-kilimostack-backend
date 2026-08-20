import { humanize } from "@/lib/format";

const sectorDot: Record<string, string> = {
  crops: "bg-moss",
  livestock: "bg-ochre",
  aquaculture: "bg-herbarium-light",
  natural_resource_management: "bg-herbarium-dark",
  cross_cutting: "bg-ink/40",
};

export function SectorChip({ sector }: { sector: string }) {
  if (!sector) return <span className="text-ink/35">—</span>;
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-ink/80">
      <span className={`h-1.5 w-1.5 rounded-full ${sectorDot[sector] ?? "bg-ink/40"}`} />
      {humanize(sector)}
    </span>
  );
}
