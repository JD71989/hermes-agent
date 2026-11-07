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
import { formatWhen } from "@/lib/guardian";
import { useGuardianSurface } from "@/hooks/useGuardianSurface";

export default function GuardianCyberlabPage() {
  const { setAfterTitle } = usePageHeader();
  const { data, error, loading, refresh } = useGuardianSurface(() => api.guardianCyberlab());

  useEffect(() => {
    setAfterTitle(
      <div className="flex flex-wrap items-center gap-2">
        <GuardianSurfaceNav active="/guardian/cyberlab" />
        <GuardianRefreshButton loading={loading} onClick={() => void refresh()} />
      </div>,
    );
    return () => setAfterTitle(null);
  }, [loading, refresh, setAfterTitle]);

  return (
    <div className="flex flex-col gap-6">
      <GuardianPageError what="Guardian CyberLab" error={error} onRetry={() => void refresh()} />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="success">DEFENSIVE RESEARCH ONLY</Badge>
        <span className="text-muted-foreground">
          Guardian does not execute arbitrary or offensive commands — the Hermes task type set is fixed and read-only.
        </span>
      </div>

      <GuardianStatGrid
        items={[
          { label: "Open research cases", value: data?.status.research_cases ?? "-" },
          { label: "Threat indicators", value: data?.status.threat_indicators ?? "-" },
          { label: "Findings", value: data?.status.findings ?? "-" },
          { label: "Highest severity", value: data?.status.highest_severity ?? "-" },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel title="Threat intelligence" hint="No source connected — honest empty state">
          <GuardianEmpty>No threat intelligence source connected.</GuardianEmpty>
        </GuardianPanel>

        <GuardianPanel title="Research cases" hint="Reuse existing record, approval and audit architecture">
          <GuardianEmpty>No research cases recorded.</GuardianEmpty>
        </GuardianPanel>

        <GuardianPanel title="Defensive recommendations" hint="Only from recorded findings">
          <GuardianEmpty>No recommendations yet.</GuardianEmpty>
        </GuardianPanel>

        <GuardianPanel title="Operating boundary" hint="What CyberLab is permitted to do">
          <div className="grid gap-2 text-xs">
            {(data?.boundary.allowed ?? []).map((item) => (
              <div key={item} className="border border-border bg-surface px-3 py-2">
                <strong>Allowed</strong> — {item}
              </div>
            ))}
            {(data?.boundary.forbidden ?? []).map((item) => (
              <div key={item} className="border border-destructive/40 bg-destructive/10 px-3 py-2 text-destructive">
                <strong>Forbidden</strong> — {item}
              </div>
            ))}
          </div>
        </GuardianPanel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel title="Vault posture" hint="Encrypted credential control plane status" source={data?.vault.source}>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            <div className="contents">
              <dt className="text-muted-foreground">Status</dt>
              <dd>{data?.vault.status ?? "-"}</dd>
            </div>
            <div className="contents">
              <dt className="text-muted-foreground">Source</dt>
              <dd className="break-all font-mono-ui text-[11px]">{data?.vault.source.path ?? "not found"}</dd>
            </div>
          </dl>
        </GuardianPanel>

        <GuardianPanel title="Physical security" hint="Defensive hardening — read-only" source={data?.physical_security.source}>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            <div className="contents">
              <dt className="text-muted-foreground">Status</dt>
              <dd>{data?.physical_security.status ?? "-"}</dd>
            </div>
            <div className="contents">
              <dt className="text-muted-foreground">Source</dt>
              <dd className="break-all font-mono-ui text-[11px]">{data?.physical_security.source.path ?? "not found"}</dd>
            </div>
          </dl>
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
          <GuardianEmpty>No CyberLab cron jobs matched.</GuardianEmpty>
        )}
      </GuardianPanel>
    </div>
  );
}
