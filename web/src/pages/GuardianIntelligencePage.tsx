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
import { cell, formatBytes, formatWhen } from "@/lib/guardian";
import { useGuardianSurface } from "@/hooks/useGuardianSurface";

const WORKFLOW_TONE: Record<string, "success" | "warning" | "destructive" | "outline"> = {
  completed: "success",
  running: "warning",
  failed: "destructive",
  error: "destructive",
};

export default function GuardianIntelligencePage() {
  const { setAfterTitle } = usePageHeader();
  const { data, error, loading, refresh } = useGuardianSurface(() => api.guardianIntelligence());

  useEffect(() => {
    setAfterTitle(
      <div className="flex flex-wrap items-center gap-2">
        <GuardianSurfaceNav active="/guardian/intelligence" />
        <GuardianRefreshButton loading={loading} onClick={() => void refresh()} />
      </div>,
    );
    return () => setAfterTitle(null);
  }, [loading, refresh, setAfterTitle]);

  const queue = data?.opportunity_intelligence.queue;
  const live = data?.opportunity_intelligence.live_targets;

  return (
    <div className="flex flex-col gap-6">
      <GuardianPageError what="Guardian intelligence" error={error} onRetry={() => void refresh()} />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone={data?.policy.live_trading_enabled ? "destructive" : "success"}>
          {data?.policy.live_trading_enabled ? "LIVE TRADING ENABLED" : "RESEARCH & PAPER ONLY"}
        </Badge>
        <span className="text-muted-foreground">
          Market and opportunity intelligence is discovery-only. Execution, leverage and withdrawals stay off until
          separately authorised.
        </span>
      </div>

      <GuardianStatGrid
        items={[
          { label: "Scored opportunities", value: String(queue?.items.length ?? 0) },
          {
            label: "Claimed value (USD)",
            value: queue?.verified_revenue_usd === null || queue?.verified_revenue_usd === undefined
              ? "-"
              : Number(queue.verified_revenue_usd).toLocaleString(),
          },
          { label: "Live targets", value: String(live?.items.length ?? 0) },
          { label: "Research artifacts", value: String(data?.research.artifacts.length ?? 0) },
        ]}
      />

      <GuardianPanel
        title="Opportunity intelligence"
        hint={
          queue
            ? `status ${String(queue.status ?? "unknown")} · ${String(queue.external_submissions ?? 0)} external submissions`
            : "Scored commercial opportunities"
        }
        source={queue?.source}
      >
        {queue && queue.items.length > 0 ? (
          <GuardianTable head={["Opportunity", "Value (USD)", "Fit", "Eligibility", "Verified"]}>
            {queue.items.map((item, index) => {
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
                    <div className="text-[11px] text-muted-foreground">{cell(item, ["evidence"])}</div>
                  </GuardianTd>
                  <GuardianTd className="font-mono-ui text-xs">
                    {item.value_usd === null || item.value_usd === undefined ? "-" : Number(item.value_usd).toLocaleString()}
                  </GuardianTd>
                  <GuardianTd className="text-xs">{cell(item, ["fit"])}</GuardianTd>
                  <GuardianTd className="text-xs text-muted-foreground">{cell(item, ["eligibility"])}</GuardianTd>
                  <GuardianTd className="text-xs text-muted-foreground">{cell(item, ["source_verified"])}</GuardianTd>
                </GuardianTr>
              );
            })}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No scored opportunity queue found for this install.</GuardianEmpty>
        )}
      </GuardianPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel
          title="Live targets"
          hint="Opportunities that passed the score gate and still need explicit approval"
          source={live?.source}
        >
          {live && live.items.length > 0 ? (
            <GuardianTable head={["Target", "Value (USD)", "Action", "Approval"]}>
              {live.items.map((item, index) => {
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
                      {item.value_usd === null || item.value_usd === undefined ? "-" : Number(item.value_usd).toLocaleString()}
                    </GuardianTd>
                    <GuardianTd className="text-xs">{cell(item, ["action"])}</GuardianTd>
                    <GuardianTd>
                      <Badge tone={item.approval_required ? "warning" : "outline"}>
                        {item.approval_required ? "required" : "not required"}
                      </Badge>
                    </GuardianTd>
                  </GuardianTr>
                );
              })}
            </GuardianTable>
          ) : (
            <GuardianEmpty>
              {live ? `Targets status: ${String(live.status ?? "unknown")}.` : "No live target file found."}
            </GuardianEmpty>
          )}
        </GuardianPanel>

        <GuardianPanel
          title="Last intelligence run"
          hint="The most recent generator pass and how much it produced"
          source={data?.opportunity_intelligence.last_run.source}
        >
          <GuardianStatGrid
            items={[
              { label: "Status", value: String(data?.opportunity_intelligence.last_run.status ?? "-") },
              { label: "Items produced", value: String(data?.opportunity_intelligence.last_run.count ?? "-") },
              {
                label: "Generated",
                value: formatWhen(data?.opportunity_intelligence.last_run.generated_at),
              },
            ]}
          />
        </GuardianPanel>
      </div>

      <GuardianPanel
        title="Research artifacts"
        hint="Scripts and notes in the repository's research directory"
        source={data?.research.source}
      >
        {data && data.research.artifacts.length > 0 ? (
          <GuardianTable head={["Artifact", "Kind", "Size", "Updated"]}>
            {data.research.artifacts.map((artifact) => (
              <GuardianTr key={artifact.name}>
                <GuardianTd className="font-mono-ui text-xs">{artifact.name}</GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{artifact.kind}</GuardianTd>
                <GuardianTd className="font-mono-ui text-xs">{formatBytes(artifact.size_bytes)}</GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{formatWhen(artifact.updated_at)}</GuardianTd>
              </GuardianTr>
            ))}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No research artifacts found.</GuardianEmpty>
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

      <GuardianPanel title="Capabilities" hint="Intelligence modules present on this install (names only for credentials)">
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
            </span>
          ))}
          {(!data || data.capabilities.length === 0) && <GuardianEmpty>No capabilities registered.</GuardianEmpty>}
        </div>
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
          <GuardianEmpty>No intelligence cron jobs matched.</GuardianEmpty>
        )}
      </GuardianPanel>
    </div>
  );
}
