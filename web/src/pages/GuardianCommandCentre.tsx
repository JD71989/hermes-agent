import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { api } from "@/lib/api";
import { usePageHeader } from "@/contexts/usePageHeader";
import {
  GuardianEmpty,
  GuardianPageError,
  GuardianPanel,
  GuardianRefreshButton,
  GuardianStatGrid,
  GuardianSurfaceNav,
} from "@/components/GuardianSurface";
import { GUARDIAN_SURFACES } from "@/lib/guardian";
import { useGuardianSurface } from "@/hooks/useGuardianSurface";

const DEPARTMENT_CARDS = [
  {
    title: "Business & Revenue",
    path: "/guardian/revenue",
    description: "Portfolio experiments, revenue engines, verified evidence and approvals.",
    detail: "Paper & research only — live trading locked.",
  },
  {
    title: "Marketing",
    path: "/guardian/marketing",
    description: "Traffic lanes, growth funnel, campaigns and distribution.",
    detail: "Measured traffic only — no invented numbers.",
  },
  {
    title: "Media & Creators",
    path: "/guardian/creators",
    description: "Creator identities, social mesh, writing revenue and media farm.",
    detail: "Human publication approval gate.",
  },
  {
    title: "Crypto",
    path: "/guardian/crypto",
    description: "Solana launch intelligence, risk gate and paper-trade signals.",
    detail: "Detector ready — live execution gated.",
  },
  {
    title: "Trading",
    path: "/guardian/trading",
    description: "Pump.fun, Polymarket and Pionex paper lanes with workflow evidence.",
    detail: "Paper only — leverage & withdrawals locked.",
  },
  {
    title: "Intelligence & Research",
    path: "/guardian/intelligence",
    description: "Scored opportunities, live targets, research artifacts and workflows.",
    detail: "Discovery only — no fabricated findings.",
  },
  {
    title: "CyberLab",
    path: "/guardian/cyberlab",
    description: "Defensive security research, threat intelligence and hardening.",
    detail: "Defensive only — no offensive execution.",
  },
  {
    title: "Automation",
    path: "/guardian/automation",
    description: "Cron jobs, workflow controller, approvals and task queue.",
    detail: "Existing Hermes scheduler — no new orchestrator.",
  },
  {
    title: "System Administration",
    path: "/guardian/system",
    description: "Storage, databases, cron health and links to Hermes native pages.",
    detail: "Hermes native — config/keys/models stay on their pages.",
  },
] as const;

export default function GuardianCommandCentre() {
  const { setAfterTitle } = usePageHeader();
  const load = useCallback(async () => {
    const [revenue, marketing, creators, intelligence, crypto, trading, automation, system] = await Promise.all([
      api.guardianRevenue(),
      api.guardianMarketing(),
      api.guardianCreators(),
      api.guardianIntelligence(),
      api.guardianCrypto(),
      api.guardianTrading(),
      api.guardianAutomation(),
      api.guardianSystem(),
    ]);
    return { revenue, marketing, creators, intelligence, crypto, trading, automation, system };
  }, []);
  const { data, error, loading, refresh } = useGuardianSurface(load);

  useEffect(() => {
    setAfterTitle(
      <div className="flex flex-wrap items-center gap-2">
        <GuardianSurfaceNav active="/guardian" />
        <GuardianRefreshButton loading={loading} onClick={() => void refresh()} />
      </div>,
    );
    return () => setAfterTitle(null);
  }, [loading, refresh, setAfterTitle]);

  const [command, setCommand] = useState("");
  const [event, setEvent] = useState<string | null>(null);
  const runMission = useCallback(async () => {
    const mission = command.trim();
    if (!mission) return;
    try {
      const workflow = await api.launchGuardianWorkflow({
        engine: "general",
        name: "Guardian Mission · " + mission.slice(0, 42),
        mission,
        profile: "default",
      });
      setEvent(`Mission workflow launched · ${workflow.id}`);
      setCommand("");
    } catch {
      setEvent("Mission workflow failed to launch");
    }
  }, [command]);

  return (
    <div className="flex flex-col gap-6">
      <GuardianPageError what="Guardian command centre" error={error} onRetry={() => void refresh()} />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone={data?.revenue.policy.live_trading_enabled ? "destructive" : "success"}>
          {data?.revenue.policy.live_trading_enabled ? "LIVE TRADING ENABLED" : "PAPER & RESEARCH ONLY"}
        </Badge>
        <span className="text-muted-foreground">
          Guardian V5 capabilities inside Hermes — one control centre, no separate application.
        </span>
      </div>

      <GuardianStatGrid
        items={[
          { label: "Portfolio experiments", value: String(data?.revenue.portfolio.counts.total ?? 0) },
          { label: "CRM contacts", value: String(data?.revenue ? (data.marketing?.funnel.crm_contacts ?? 0) : 0) },
          { label: "Creator identities", value: String(data?.creators.creator_manifest.count ?? 0) },
          { label: "Cron jobs", value: String(data?.automation.cron.jobs.length ?? 0) },
        ]}
      />

      <GuardianPanel title="Mission command" hint="Launch a Guardian workflow from the unified controller">
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void runMission()}
            placeholder="Describe the mission…"
            className="flex-1 border border-border/60 bg-background px-3 py-2 text-sm outline-none focus:border-border"
          />
          <button
            type="button"
            onClick={() => void runMission()}
            disabled={loading || !command.trim()}
            className="border border-border/60 px-4 py-2 text-xs uppercase tracking-[0.12em] hover:border-border disabled:opacity-50"
          >
            Run
          </button>
        </div>
        {event && <p className="mt-2 text-[11px] text-muted-foreground">{event}</p>}
      </GuardianPanel>

      <GuardianPanel title="Departments" hint="Guardian V5 capabilities organised into 9 Hermes departments">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {DEPARTMENT_CARDS.map((card) => (
            <Link
              key={card.path}
              to={card.path}
              className="flex flex-col gap-2 border border-border/60 p-4 transition-colors hover:border-border hover:bg-secondary/20"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium">{card.title}</span>
                <Badge tone="outline">Open</Badge>
              </div>
              <p className="text-xs text-muted-foreground">{card.description}</p>
              <p className="text-[11px] text-muted-foreground">{card.detail}</p>
            </Link>
          ))}
        </div>
      </GuardianPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel title="Business & Revenue at a glance" hint="Portfolio, evidence and approvals">
          {data ? (
            <div className="grid gap-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Experiments</span>
                <span className="font-mono-ui">{data.revenue.portfolio.counts.total}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Ready for review</span>
                <span className="font-mono-ui">{data.revenue.portfolio.counts.READY_FOR_REVIEW ?? 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Pending approvals</span>
                <span className="font-mono-ui">{data.revenue.approvals.pending}</span>
              </div>
              <Link to="/guardian/revenue" className="text-xs hover:underline">
                Open Business & Revenue
              </Link>
            </div>
          ) : (
            <GuardianEmpty>No revenue data available.</GuardianEmpty>
          )}
        </GuardianPanel>

        <GuardianPanel title="Media & Creators at a glance" hint="Pipeline between research and publication">
          {data ? (
            <div className="flex flex-wrap gap-1.5">
              {data.creators.pipeline.map((stage) => (
                <Badge key={stage.stage} tone="outline">
                  {stage.stage}: {stage.count}
                </Badge>
              ))}
            </div>
          ) : (
            <GuardianEmpty>No creator data available.</GuardianEmpty>
          )}
        </GuardianPanel>
      </div>

      <GuardianPanel title="Quick links" hint="Hermes native areas — no duplication">
        <ul className="grid gap-2 text-xs sm:grid-cols-3">
          {[
            ["/cron", "Cron"],
            ["/skills", "Skills"],
            ["/models", "Models"],
            ["/logs", "Logs"],
            ["/system", "System"],
            ["/guardian/vault", "Vault"],
          ].map(([path, label]) => (
            <li key={path}>
              <Link to={path} className="block border border-border/60 px-3 py-2 hover:border-border">
                {label}
              </Link>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-[11px] text-muted-foreground">
          {GUARDIAN_SURFACES.length} Guardian surfaces in the tab strip — Command Centre is the hub.
        </p>
      </GuardianPanel>
    </div>
  );
}
