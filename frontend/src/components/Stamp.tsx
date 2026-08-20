import clsx from "clsx";
import { humanize } from "@/lib/format";
import type { QualityFlag, RiskLevel, CurrencyStatus, AccuracyCheck } from "@/types";

type StampTone = "herbarium" | "moss" | "ochre" | "rust" | "neutral";

const toneClasses: Record<StampTone, string> = {
  herbarium: "border-herbarium text-herbarium bg-herbarium/[0.06]",
  moss: "border-moss-dark text-moss-dark bg-moss/[0.08]",
  ochre: "border-ochre-dark text-ochre-dark bg-ochre/[0.10]",
  rust: "border-rust text-rust bg-rust/[0.08]",
  neutral: "border-ink/25 text-ink/50 bg-transparent",
};

export function Stamp({ label, tone = "neutral" }: { label: string; tone?: StampTone }) {
  return <span className={clsx("stamp", toneClasses[tone])}>{label}</span>;
}

const qualityFlagTone: Record<string, StampTone> = {
  ready_to_certify: "herbarium",
  needs_review: "ochre",
  needs_update: "ochre",
  duplicate: "neutral",
  reject: "rust",
  "": "neutral",
};

export function QualityFlagStamp({ value }: { value: QualityFlag }) {
  return <Stamp label={value ? humanize(value) : "Unscreened"} tone={qualityFlagTone[value ?? ""] ?? "neutral"} />;
}

const riskTone: Record<string, StampTone> = {
  low: "moss",
  medium: "ochre",
  high: "rust",
  "": "neutral",
};

export function RiskLevelStamp({ value }: { value: RiskLevel }) {
  return <Stamp label={value ? `${humanize(value)} risk` : "Risk unknown"} tone={riskTone[value ?? ""] ?? "neutral"} />;
}

const currencyTone: Record<string, StampTone> = {
  current: "moss",
  needs_update: "ochre",
  outdated: "rust",
  needs_verification: "neutral",
  "": "neutral",
};

export function CurrencyStatusStamp({ value }: { value: CurrencyStatus }) {
  return <Stamp label={value ? humanize(value) : "Not checked"} tone={currencyTone[value ?? ""] ?? "neutral"} />;
}

const accuracyTone: Record<string, StampTone> = {
  verified: "herbarium",
  needs_review: "ochre",
  flagged_inaccurate: "rust",
  "": "neutral",
};

export function AccuracyStamp({ value }: { value: AccuracyCheck }) {
  return <Stamp label={value ? humanize(value) : "Not checked"} tone={accuracyTone[value ?? ""] ?? "neutral"} />;
}
