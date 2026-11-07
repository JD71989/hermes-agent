import { useEffect } from "react";
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
  GuardianTable,
  GuardianTd,
  GuardianTr,
} from "@/components/GuardianSurface";
import { cell, formatMoney, formatWhen } from "@/lib/guardian";
import { useGuardianSurface } from "@/hooks/useGuardianSurface";

const STATE_TONE: Record<string, "success" | "warning" | "destructive" | "outline"> = {
  ACTIVE: "success",
  READY_FOR_REVIEW: "success",
  IN_PROGRESS: "warning",
  NEEDS_VERIFICATION: "warning",
  QUEUED: "outline",
  BLOCKED: "destructive",
};

function stateTone(state: string) {
  return STATE_TONE[state.toUpperCase()] ?? "outline";
}

export default function GuardianRevenuePage() {
  const { setAfterTitle } = usePageHeader();
  const { data, error, loading, refresh } = useGuardianSurface(() => api.guardianRevenue());

  useEffect(() => {
    setAfterTitle(
      <div className="flex flex-wrap items-center gap-2">
        <GuardianSurfaceNav active="/guardian/revenue" />
        <GuardianRefreshButton loading={loading} onClick={() => void refresh()} />
      </div>,
    );
    return () => setAfterTitle(null);
  }, [loading, refresh, setAfterTitle]);

  const policy = data?.policy ?? {};
  const liveTrading = policy.live_trading_enabled === true;

  return (
    <div className="flex flex-col gap-6">
      <GuardianPageError what="Guardian revenue" error={error} onRetry={() => void refresh()} />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone={liveTrading ? "destructive" : "success"}>
          {liveTrading ? "LIVE TRADING ENABLED" : "PAPER & RESEARCH ONLY"}
        </Badge>
        <span className="text-muted-foreground">
          withdrawals {policy.withdrawals_enabled ? "enabled" : "disabled"} · leverage{" "}
          {policy.leverage_enabled ? "enabled" : "disabled"} · verified revenue required{" "}
          {policy.verified_revenue_required ? "yes" : "not configured"}
        </span>
      </div>

      <GuardianStatGrid
        items={[
          { label: "Portfolio experiments", value: String(data?.portfolio.counts.total ?? 0) },
          { label: "Ready for review", value: String(data?.portfolio.counts.READY_FOR_REVIEW ?? 0) },
          { label: "Verified revenue", value: formatMoney(data?.evidence.paid_totals ?? {}) },
          { label: "Pending approvals", value: String(data?.approvals.pending ?? 0) },
        ]}
      />

      <GuardianPanel
        title="Revenue portfolio"
        hint={
          data
            ? Object.entries(data.portfolio.counts)
                .filter(([key]) => key !== "total")
                .map(([key, count]) => `${count} ${key.toLowerCase().replace(/_/g, " ")}`)
                .join(" · ")
            : "Portfolio experiment states"
        }
        source={data?.portfolio.source}
      >
        {data && data.portfolio.experiments.length > 0 ? (
          <GuardianTable head={["Experiment", "State", "Tier", "Model", "Reason"]}>
            {data.portfolio.experiments.map((experiment) => (
              <GuardianTr key={experiment.id}>
                <GuardianTd>
                  <div className="text-sm">{experiment.name}</div>
                  <div className="font-mono-ui text-[11px] text-muted-foreground">{experiment.id}</div>
                </GuardianTd>
                <GuardianTd>
                  <Badge tone={stateTone(experiment.effective_state ?? experiment.state)}>
                    {experiment.effective_state ?? experiment.state}
                  </Badge>
                </GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{experiment.tier ?? "-"}</GuardianTd>
                <GuardianTd className="font-mono-ui text-[11px] text-muted-foreground">
                  {experiment.model_profile ?? "-"}
                </GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{experiment.reason ?? "-"}</GuardianTd>
              </GuardianTr>
            ))}
          </GuardianTable>
        ) : (
          <GuardianEmpty>
            No portfolio manifest found. Set <code>guardian.revenue_root</code> or place{" "}
            <code>guardian_portfolio_experiments.json</code> in the LEADGEN checkout.
          </GuardianEmpty>
        )}
      </GuardianPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel
          title="Revenue fabric engines"
          hint={data?.revenue_fabric.principle ?? "Activated engines and their monetization paths"}
          source={data?.revenue_fabric.source}
        >
          {data && data.revenue_fabric.engines.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {data.revenue_fabric.engines.map((engine, index) => (
                <li key={String(engine.id ?? index)} className="flex flex-wrap items-center gap-2 border-b border-border/40 pb-2 last:border-0 last:pb-0">
                  <span className="w-40 font-mono-ui text-xs">{String(engine.id ?? "engine")}</span>
                  <Badge tone={String(engine.status ?? "").includes("ACTIVE") ? "success" : "outline"}>
                    {String(engine.status ?? "unknown")}
                  </Badge>
                  <span className="text-[11px] text-muted-foreground">
                    {(engine.monetization ?? []).join(" · ")}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <GuardianEmpty>No activation manifest found.</GuardianEmpty>
          )}
        </GuardianPanel>

        <GuardianPanel
          title="Campaign targets"
          hint="Offers that still need configuration before they can produce revenue"
          source={data?.revenue_fabric.source}
        >
          {data && data.revenue_fabric.campaign_targets.length > 0 ? (
            <ul className="flex flex-col gap-3">
              {data.revenue_fabric.campaign_targets.map((target, index) => (
                <li key={String(target.name ?? index)}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm">{String(target.name ?? "target")}</span>
                    <Badge tone="outline">{String(target.status ?? "unknown")}</Badge>
                  </div>
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    Requires: {(target.details_required ?? []).join(", ") || "no listed blockers"}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <GuardianEmpty>No campaign targets configured.</GuardianEmpty>
          )}
        </GuardianPanel>
      </div>

      <GuardianPanel
        title="Opportunity queue"
        hint={
          data
            ? `${String(data.opportunities.items.length)} queued · ${String(data.opportunities.external_submissions ?? 0)} external submissions · ${String(data.opportunities.approval_rule ?? "approval rule unknown")}`
            : "Scored opportunities awaiting a human decision"
        }
        source={data?.opportunities.source}
      >
        {data && data.opportunities.items.length > 0 ? (
          <GuardianTable head={["Opportunity", "Value (USD)", "Fit", "Eligibility", "Verified"]}>
            {data.opportunities.items.map((item, index) => {
              const url = typeof item.url === "string" ? item.url : null;
              return (
                <GuardianTr key={String(item.id ?? item.url ?? index)}>
                  <GuardianTd>
                    {url ? (
                      <a className="hover:underline" href={url} rel="noreferrer" target="_blank">
                        {cell(item, ["title", "name"])}
                      </a>
                    ) : (
                      cell(item, ["title", "name"])
                    )}
                  </GuardianTd>
                  <GuardianTd className="font-mono-ui text-xs">
                    {item.value_usd === null || item.value_usd === undefined
                      ? "-"
                      : Number(item.value_usd).toLocaleString()}
                  </GuardianTd>
                  <GuardianTd className="text-xs">{cell(item, ["fit"])}</GuardianTd>
                  <GuardianTd className="text-xs text-muted-foreground">{cell(item, ["eligibility"])}</GuardianTd>
                  <GuardianTd className="text-xs text-muted-foreground">{cell(item, ["source_verified"])}</GuardianTd>
                </GuardianTr>
              );
            })}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No actionable opportunities. The queue generator has not produced a scored batch.</GuardianEmpty>
        )}
      </GuardianPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel
          title="Verified revenue evidence"
          hint={data?.evidence.note ?? "Local evidence ledger"}
          source={data?.evidence.source}
        >
          <GuardianStatGrid
            items={[
              { label: "Ledger records", value: String(data?.evidence.records ?? 0) },
              { label: "Distinct leads", value: String(data?.evidence.leads ?? 0) },
              { label: "Verified total", value: formatMoney(data?.evidence.paid_totals ?? {}) },
            ]}
          />
          <p className="mt-3 text-[11px] text-muted-foreground">
            Only the latest event per lead counts, and only a <code>PAID</code> event adds to the total. A later
            refund removes that lead&apos;s revenue.
          </p>
        </GuardianPanel>

        <GuardianPanel
          title="Pending approvals"
          hint="Work that cannot proceed without an operator decision"
          source={data?.approvals.source}
        >
          {data && data.approvals.items.length > 0 ? (
            <GuardianTable head={["Item", "Status", "Detail"]}>
              {data.approvals.items.map((item, index) => (
                <GuardianTr key={String(item.id ?? index)}>
                  <GuardianTd className="text-xs">{cell(item, ["title", "name", "id"])}</GuardianTd>
                  <GuardianTd className="text-xs">{cell(item, ["status"])}</GuardianTd>
                  <GuardianTd className="text-xs text-muted-foreground">
                    {cell(item, ["detail", "reason", "action"])}
                  </GuardianTd>
                </GuardianTr>
              ))}
            </GuardianTable>
          ) : (
            <GuardianEmpty>
              {data?.approvals.total ? `${String(data.approvals.total)} approvals, none pending.` : "No approval queue found."}
            </GuardianEmpty>
          )}
        </GuardianPanel>
      </div>

      <GuardianPanel title="Automation" hint="Hermes cron jobs that feed this surface">
        {data && data.automation.jobs.length > 0 ? (
          <GuardianTable head={["Job", "Schedule", "Last status", "Last run"]}>
            {data.automation.jobs.map((job) => (
              <GuardianTr key={job.id}>
                <GuardianTd>
                  <div className="text-sm">{job.name}</div>
                  {!job.enabled && <div className="text-[11px] text-muted-foreground">disabled</div>}
                </GuardianTd>
                <GuardianTd className="font-mono-ui text-[11px]">{job.schedule || "-"}</GuardianTd>
                <GuardianTd className="text-xs">
                  {job.last_status ? <Badge tone={job.last_status === "success" ? "success" : "warning"}>{job.last_status}</Badge> : "-"}
                </GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{formatWhen(job.last_run)}</GuardianTd>
              </GuardianTr>
            ))}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No revenue cron jobs matched.</GuardianEmpty>
        )}
      </GuardianPanel>

      <GuardianPanel title="Capabilities" hint="Modules present on this install, and the credentials they need (names only)">
        <div className="flex flex-wrap gap-2">
          {(data?.capabilities ?? []).map((capability) => (
            <span
              key={capability.id}
              className="flex items-center gap-2 border border-border/60 px-2 py-1 text-[11px]"
              title={capability.module}
            >
              {capability.label}
              <Badge tone={capability.present ? "success" : "warning"}>
                {capability.present ? "module ready" : "module missing"}
              </Badge>
              {capability.required_credentials.length > 0 && (
                <span className="text-muted-foreground">
                  {capability.required_credentials.join(", ")} {capability.credentials_present ? "present" : "missing"}
                </span>
              )}
            </span>
          ))}
          {(!data || data.capabilities.length === 0) && <GuardianEmpty>No capabilities registered.</GuardianEmpty>}
        </div>
      </GuardianPanel>
    </div>
  );
}
