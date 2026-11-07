import type { GuardianSource } from "@/lib/api";

/** The Guardian capability families — 9 departments + Command Centre + Vault. */
export const GUARDIAN_SURFACES = [
  { path: "/guardian", label: "Command Centre" },
  { path: "/guardian/revenue", label: "Business & Revenue" },
  { path: "/guardian/marketing", label: "Marketing" },
  { path: "/guardian/creators", label: "Media & Creators" },
  { path: "/guardian/crypto", label: "Crypto" },
  { path: "/guardian/trading", label: "Trading" },
  { path: "/guardian/intelligence", label: "Intelligence" },
  { path: "/guardian/cyberlab", label: "CyberLab" },
  { path: "/guardian/automation", label: "Automation" },
  { path: "/guardian/system", label: "System Admin" },
  { path: "/guardian/vault", label: "Vault" },
] as const;

export type GuardianSurfaceKey = (typeof GUARDIAN_SURFACES)[number]["path"];

export function formatWhen(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "-";
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

/**
 * Totals from the evidence ledger. An empty ledger prints "unverified" rather
 * than "0", because zero revenue and unproven revenue are different claims.
 */
export function formatMoney(totals: Record<string, number>): string {
  const entries = Object.entries(totals);
  if (entries.length === 0) return "0 (unverified)";
  return entries.map(([currency, amount]) => `${currency} ${amount.toFixed(2)}`).join(" + ");
}

/** First non-empty string field out of `keys` — surfaces come from varied stores. */
export function cell(row: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = row[key];
    if (value === null || value === undefined) continue;
    if (typeof value === "string" && value.trim() !== "") return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value)) return value.join(", ");
  }
  return "-";
}

/**
 * The label a source badge shows. Kept separate from the component so the
 * "missing store is not an empty store" rule is testable on its own.
 */
export function sourceLabel(source: GuardianSource | undefined, label?: string): string {
  if (!source) return label ?? "no source";
  if (source.available) return label ?? "live";
  if (source.configured) return label ?? source.error ?? "unreadable";
  return label ?? "not found";
}
