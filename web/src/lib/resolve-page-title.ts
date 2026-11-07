import type { Translations } from "@/i18n/types";

const BUILTIN: Record<string, keyof Translations["app"]["nav"]> = {
  "/chat": "chat",
  "/sessions": "sessions",
  "/analytics": "analytics",
  "/models": "models",
  "/logs": "logs",
  "/cron": "cron",
  "/skills": "skills",
  "/plugins": "plugins",
  "/profiles": "profiles",
  "/config": "config",
  "/env": "keys",
  "/docs": "documentation",
};

// Built-in routes without an i18n nav key. Keep these in sync with the
// sidebar labels in App.tsx — the naive capitalize fallback below mangles
// initialisms ("/mcp" → "Mcp") and can't match multi-word labels.
const BUILTIN_LITERAL: Record<string, string> = {
  "/files": "Files",
  "/mcp": "MCP",
  "/channels": "Channels",
  "/webhooks": "Webhooks",
  "/pairing": "Pairing",
  "/system": "System",
  // Guardian surfaces. One sidebar entry (/guardian) hosts an in-page tab
  // strip, so these paths resolve their own titles rather than reusing it.
  "/guardian": "Guardian Command Centre",
  "/guardian/vault": "Guardian Vault",
  "/guardian/revenue": "Guardian Business & Revenue",
  "/guardian/commercial": "Guardian Commercial",
  "/guardian/marketing": "Guardian Marketing",
  "/guardian/creators": "Guardian Media & Creators",
  "/guardian/crypto": "Guardian Crypto",
  "/guardian/trading": "Guardian Trading",
  "/guardian/intelligence": "Guardian Intelligence",
  "/guardian/cyberlab": "Guardian CyberLab",
  "/guardian/automation": "Guardian Automation",
  "/guardian/system": "Guardian System Admin",
};

export function resolvePageTitle(
  pathname: string,
  t: Translations,
  pluginTabs: { path: string; label: string }[],
): string {
  const normalized = pathname.replace(/\/$/, "") || "/";
  if (normalized === "/") {
    return t.app.nav.sessions;
  }
  const plugin = pluginTabs.find((p) => p.path === normalized);
  if (plugin) {
    return plugin.label;
  }
  const key = BUILTIN[normalized];
  if (key) {
    return t.app.nav[key];
  }
  const literal = BUILTIN_LITERAL[normalized];
  if (literal) {
    return literal;
  }
  // Derive title from pathname: "/profiles" → "Profiles"
  const segment = normalized.slice(1);
  if (segment) {
    return segment.charAt(0).toUpperCase() + segment.slice(1);
  }
  return t.app.webUi;
}
