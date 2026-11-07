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
import { cell, formatWhen } from "@/lib/guardian";
import { useGuardianSurface } from "@/hooks/useGuardianSurface";

const WORKFLOW_TONE: Record<string, "success" | "warning" | "destructive" | "outline"> = {
  completed: "success",
  running: "warning",
  failed: "destructive",
  error: "destructive",
};

export default function GuardianTradingPage() {
  const { setAfterTitle } = usePageHeader();
  const { data, error, loading, refresh } = useGuardianSurface(() => api.guardianTrading());

  useEffect(() => {
    setAfterTitle(
      <div className="flex flex-wrap items-center gap-2">
        <GuardianSurfaceNav active="/guardian/trading" />
        <GuardianRefreshButton loading={loading} onClick={() => void refresh()} />
      </div>,
    );
    return () => setAfterTitle(null);
  }, [loading, refresh, setAfterTitle]);

  return (
    <div className="flex flex-col gap-6">
      <GuardianPageError what="Guardian trading" error={error} onRetry={() => void refresh()} />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone={data?.policy.live_trading_enabled ? "destructive" : "success"}>
          {data?.policy.live_trading_enabled ? "LIVE TRADING ENABLED" : "PAPER ONLY — LIVE LOCKED"}
        </Badge>
        <span className="text-muted-foreground">
          Research and paper trading only. Execution, leverage and withdrawals stay off until separately authorised.
        </span>
      </div>

      <GuardianStatGrid
        items={[
          { label: "Lanes", value: String(data?.lanes.length ?? 0) },
          {
            label: "Scored opportunities",
            value: String(data?.opportunity_intelligence.queue.items.length ?? 0),
          },
          { label: "Live targets", value: String(data?.opportunity_intelligence.live_targets.items.length ?? 0) },
          { label: "Workflows", value: String(data?.workflows.length ?? 0) },
        ]}
      />

      <GuardianPanel title="Trading lanes" hint="Paper lanes — no funds exposed">
        {data && data.lanes.length > 0 ? (
          <GuardianTable head={["Lane", "Mode", "Status"]}>
            {data.lanes.map((lane) => (
              <GuardianTr key={lane.lane}>
                <GuardianTd className="text-sm">{lane.lane}</GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{lane.mode}</GuardianTd>
                <GuardianTd>
                  <Badge tone="success">{lane.status}</Badge>
                </GuardianTd>
              </GuardianTr>
            ))}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No trading lanes configured.</GuardianEmpty>
        )}
      </GuardianPanel>

      <GuardianPanel title="Opportunity intelligence" hint="Scored opportunities awaiting approval">
        {data && data.opportunity_intelligence.queue.items.length > 0 ? (
          <GuardianTable head={["Opportunity", "Value (USD)", "Fit", "Eligibility"]}>
            {data.opportunity_intelligence.queue.items.map((item, index) => (
              <GuardianTr key={String(item.id ?? item.url ?? index)}>
                <GuardianTd>
                  {typeof item.url === "string" ? (
                    <a className="hover:underline" href={item.url as string} rel="noreferrer" target="_blank">
                      {cell(item, ["title", "name"])}
                    </a>
                  ) : (
                    cell(item, ["title", "name"])
                  )}
                </GuardianTd>
                <GuardianTd className="font-mono-ui text-xs">
                  {item.value_usd === null || item.value_usd === undefined ? "-" : Number(item.value_usd).toLocaleString()}
                </GuardianTd>
                <GuardianTd className="text-xs">{cell(item, ["fit"])}</GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{cell(item, ["eligibility"])}</GuardianTd>
              </GuardianTr>
            ))}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No scored opportunities found.</GuardianEmpty>
        )}
      </GuardianPanel>

      <GuardianPanel title="Guardian workflows" hint="Mission workflows launched from the command centre">
        {data && data.workflows.length > 0 ? (
          <GuardianTable head={["Workflow", "Engine", "State", "Step", "Created", "Last error"]}>
            {data.workflows.map((workflow) => (
              <GuardianTr key={workflow.id}>
                <GuardianTd>
                  <div className="text-sm">{workflow.name}</div>
                  <div className="font-mono-ui text-[11px] text-muted-foreground">{workflow.id}</div>
                </GuardianTd>
                <GuardianTd className="font-mono-ui text-xs">{workflow.engine}</GuardianTd>
                <GuardianTd>
                  <Badge tone={WORKFLOW_TONE[String(workflow.state).toLowerCase()] ?? "outline"}>{workflow.state}</Badge>
                </GuardianTd>
                <GuardianTd className="font-mono-ui text-xs">{workflow.current_step ?? "-"}</GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{formatWhen(workflow.created_at)}</GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{workflow.last_error ?? "-"}</GuardianTd>
              </GuardianTr>
            ))}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No workflows recorded.</GuardianEmpty>
        )}
      </GuardianPanel>

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
          <GuardianEmpty>No trading cron jobs matched.</GuardianEmpty>
        )}
      </GuardianPanel>
    </div>
  );
}
