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

export default function GuardianMarketingPage() {
  const { setAfterTitle } = usePageHeader();
  const { data, error, loading, refresh } = useGuardianSurface(() => api.guardianMarketing());

  useEffect(() => {
    setAfterTitle(
      <div className="flex flex-wrap items-center gap-2">
        <GuardianSurfaceNav active="/guardian/marketing" />
        <GuardianRefreshButton loading={loading} onClick={() => void refresh()} />
      </div>,
    );
    return () => setAfterTitle(null);
  }, [loading, refresh, setAfterTitle]);

  return (
    <div className="flex flex-col gap-6">
      <GuardianPageError what="Guardian marketing" error={error} onRetry={() => void refresh()} />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="success">TRAFFIC ENGINE — MEASURED ONLY</Badge>
        <span className="text-muted-foreground">
          Traffic must feed measurable opportunities. No invented traffic numbers.
        </span>
      </div>

      <GuardianStatGrid
        items={[
          { label: "Opportunities", value: String(data?.funnel.opportunities ?? 0) },
          { label: "CRM contacts", value: String(data?.funnel.crm_contacts ?? 0) },
          { label: "Writing opportunities", value: String(data?.funnel.writing_opportunities ?? 0) },
          { label: "Campaign targets", value: String(data?.funnel.campaign_targets ?? 0) },
        ]}
      />

      <GuardianPanel title="Traffic lanes" hint="One engine, multiple controlled distribution lanes">
        {data && data.lanes.length > 0 ? (
          <GuardianTable head={["Lane", "Count", "Description", "Open"]}>
            {data.lanes.map((lane) => (
              <GuardianTr key={lane.lane}>
                <GuardianTd className="text-sm">{lane.lane}</GuardianTd>
                <GuardianTd className="font-mono-ui text-xs">{lane.count}</GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{lane.description}</GuardianTd>
                <GuardianTd className="text-xs">
                  <a className="hover:underline" href={lane.target}>
                    Open
                  </a>
                </GuardianTd>
              </GuardianTr>
            ))}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No traffic lanes available.</GuardianEmpty>
        )}
      </GuardianPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel title="Funnel" hint="Measured stages — no estimates">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            {(
              [
                ["Opportunities", data?.funnel.opportunities],
                ["CRM contacts", data?.funnel.crm_contacts],
                ["Writing opportunities", data?.funnel.writing_opportunities],
                ["Writing queue", data?.funnel.writing_queue],
                ["Media content", data?.funnel.media_content],
                ["Campaign targets", data?.funnel.campaign_targets],
              ] as Array<[string, number | undefined]>
            ).map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="font-mono-ui">{value ?? "-"}</dd>
              </div>
            ))}
          </dl>
        </GuardianPanel>

        <GuardianPanel title="Campaign targets" hint="Offers needing configuration before a campaign can run">
          {data && data.campaigns.targets.length > 0 ? (
            <ul className="flex flex-col gap-3">
              {data.campaigns.targets.map((target, index) => (
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
          <GuardianEmpty>No marketing cron jobs matched.</GuardianEmpty>
        )}
      </GuardianPanel>
    </div>
  );
}
