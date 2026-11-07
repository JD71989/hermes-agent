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
  paused: "warning",
};

export default function GuardianAutomationPage() {
  const { setAfterTitle } = usePageHeader();
  const { data, error, loading, refresh } = useGuardianSurface(() => api.guardianAutomation());

  useEffect(() => {
    setAfterTitle(
      <div className="flex flex-wrap items-center gap-2">
        <GuardianSurfaceNav active="/guardian/automation" />
        <GuardianRefreshButton loading={loading} onClick={() => void refresh()} />
      </div>,
    );
    return () => setAfterTitle(null);
  }, [loading, refresh, setAfterTitle]);

  const jobs = data?.cron.jobs ?? [];
  const running = data?.workflows.filter((w) => w.state === "running").length ?? 0;
  const paused = data?.workflows.filter((w) => w.state === "paused").length ?? 0;
  const failed = data?.workflows.filter((w) => w.state === "failed").length ?? 0;
  const completed = data?.workflows.filter((w) => w.state === "completed").length ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <GuardianPageError what="Guardian automation" error={error} onRetry={() => void refresh()} />

      <GuardianStatGrid
        items={[
          { label: "Cron jobs", value: String(jobs.length) },
          { label: "Workflows running", value: String(running) },
          { label: "Workflows paused", value: String(paused) },
          { label: "Pending approvals", value: String(data?.approvals.pending ?? 0) },
        ]}
      />

      <GuardianPanel title="Guardian workflow controller" hint="Persistent multi-stage workflows backed by the Hermes execution ledger">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <GuardianStatGrid
            items={[
              { label: "Running", value: String(running) },
              { label: "Paused", value: String(paused) },
              { label: "Failed", value: String(failed) },
              { label: "Completed", value: String(completed) },
            ]}
          />
        </div>
        {data && data.workflows.length > 0 ? (
          <div className="mt-4">
            <GuardianTable head={["Workflow", "Engine", "State", "Step", "Created"]}>
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
                </GuardianTr>
              ))}
            </GuardianTable>
          </div>
        ) : (
          <GuardianEmpty>No workflows recorded. Use START-IT from the Command Centre.</GuardianEmpty>
        )}
      </GuardianPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel title="Cron jobs" hint="Existing Hermes scheduled jobs — run from /cron">
          {jobs.length > 0 ? (
            <GuardianTable head={["Job", "Schedule", "Last status"]}>
              {jobs.slice(0, 10).map((job) => (
                <GuardianTr key={job.id}>
                  <GuardianTd>
                    <div className="text-sm">{job.name}</div>
                    {!job.enabled && <div className="text-[11px] text-muted-foreground">disabled</div>}
                  </GuardianTd>
                  <GuardianTd className="font-mono-ui text-[11px]">{job.schedule || "-"}</GuardianTd>
                  <GuardianTd className="text-xs">
                    {job.last_status ? <Badge tone={job.last_status === "success" ? "success" : "warning"}>{job.last_status}</Badge> : "-"}
                  </GuardianTd>
                </GuardianTr>
              ))}
            </GuardianTable>
          ) : (
            <GuardianEmpty>No cron jobs returned.</GuardianEmpty>
          )}
        </GuardianPanel>

        <GuardianPanel title="Pending approvals" hint="Work that cannot proceed without an operator decision" source={data?.approvals.source}>
          {data && data.approvals.items.length > 0 ? (
            <GuardianTable head={["Item", "Status", "Detail"]}>
              {data.approvals.items.map((item, index) => (
                <GuardianTr key={String(item.id ?? index)}>
                  <GuardianTd className="text-xs">{cell(item, ["title", "name", "id"])}</GuardianTd>
                  <GuardianTd className="text-xs">{cell(item, ["status"])}</GuardianTd>
                  <GuardianTd className="text-xs text-muted-foreground">{cell(item, ["detail", "reason", "action"])}</GuardianTd>
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

      <GuardianPanel title="Automation jobs" hint="Hermes cron jobs matching automation patterns">
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
          <GuardianEmpty>No automation cron jobs matched.</GuardianEmpty>
        )}
      </GuardianPanel>
    </div>
  );
}
