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
import { formatBytes, formatWhen } from "@/lib/guardian";
import { useGuardianSurface } from "@/hooks/useGuardianSurface";

export default function GuardianSystemPage() {
  const { setAfterTitle } = usePageHeader();
  const { data, error, loading, refresh } = useGuardianSurface(() => api.guardianSystem());

  useEffect(() => {
    setAfterTitle(
      <div className="flex flex-wrap items-center gap-2">
        <GuardianSurfaceNav active="/guardian/system" />
        <GuardianRefreshButton loading={loading} onClick={() => void refresh()} />
      </div>,
    );
    return () => setAfterTitle(null);
  }, [loading, refresh, setAfterTitle]);

  const storage = data?.storage;

  return (
    <div className="flex flex-col gap-6">
      <GuardianPageError what="Guardian System Admin" error={error} onRetry={() => void refresh()} />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="outline">HERMES NATIVE — NO DUPLICATE SYSTEM</Badge>
        <span className="text-muted-foreground">
          This surface aggregates storage and cron. Configuration, keys and models stay on their Hermes pages.
        </span>
      </div>

      {storage && (
        <GuardianStatGrid
          items={[
            { label: "Free (GB)", value: storage.capacity ? storage.capacity.free_gb.toFixed(2) : "-" },
            { label: "Total (GB)", value: storage.capacity ? storage.capacity.total_gb.toFixed(2) : "-" },
            { label: "Used", value: storage.capacity ? `${storage.capacity.used_percent.toFixed(1)}%` : "-" },
            { label: "Hermes size (GB)", value: storage.capacity ? storage.capacity.hermes_size_gb.toFixed(2) : "-" },
          ]}
        />
      )}

      <GuardianPanel title="Department links" hint="Jump to the authoritative Hermes pages — no duplication">
        {data && data.links.length > 0 ? (
          <GuardianTable head={["Area", "Description", "Open"]}>
            {data.links.map((link) => (
              <GuardianTr key={link.path}>
                <GuardianTd className="text-sm">{link.label}</GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{link.description}</GuardianTd>
                <GuardianTd className="text-xs">
                  <a className="hover:underline" href={link.path}>
                    Open
                  </a>
                </GuardianTd>
              </GuardianTr>
            ))}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No links available.</GuardianEmpty>
        )}
      </GuardianPanel>

      <GuardianPanel title="Storage locations" hint="Capacity and location overview (integrity sweep is explicit on System page)">
        {storage && (storage.locations?.length ?? 0) > 0 ? (
          <GuardianTable head={["Location", "Size", "Readable", "Writable"]}>
            {(storage.locations ?? []).slice(0, 12).map((loc) => (
              <GuardianTr key={`${loc.name}-${loc.path}`}>
                <GuardianTd>
                  <div className="text-sm">{loc.name}</div>
                  <div className="font-mono-ui text-[11px] text-muted-foreground">{loc.path}</div>
                </GuardianTd>
                <GuardianTd className="font-mono-ui text-xs">{formatBytes(loc.size_bytes)}</GuardianTd>
                <GuardianTd>
                  <Badge tone={loc.readable ? "success" : "destructive"}>{loc.readable ? "yes" : "no"}</Badge>
                </GuardianTd>
                <GuardianTd>
                  <Badge tone={loc.writable ? "success" : "warning"}>{loc.writable ? "yes" : "no"}</Badge>
                </GuardianTd>
              </GuardianTr>
            ))}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No storage locations reported.</GuardianEmpty>
        )}
      </GuardianPanel>

      <GuardianPanel title="Cron jobs" hint="Scheduled jobs — manage from /cron">
        {data && data.cron.jobs.length > 0 ? (
          <GuardianTable head={["Job", "Schedule", "Last status", "Last run"]}>
            {data.cron.jobs.map((job) => (
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
          <GuardianEmpty>No cron jobs returned.</GuardianEmpty>
        )}
      </GuardianPanel>
    </div>
  );
}
