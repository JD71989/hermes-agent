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

export default function GuardianCreatorsPage() {
  const { setAfterTitle } = usePageHeader();
  const { data, error, loading, refresh } = useGuardianSurface(() => api.guardianCreators());

  useEffect(() => {
    setAfterTitle(
      <div className="flex flex-wrap items-center gap-2">
        <GuardianSurfaceNav active="/guardian/creators" />
        <GuardianRefreshButton loading={loading} onClick={() => void refresh()} />
      </div>,
    );
    return () => setAfterTitle(null);
  }, [loading, refresh, setAfterTitle]);

  const meshCampaign = data?.social_mesh.campaign;
  const mediaCounts = Object.entries(data?.media_farm.counts ?? {});

  return (
    <div className="flex flex-col gap-6">
      <GuardianPageError what="Guardian creators" error={error} onRetry={() => void refresh()} />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone={data?.youtube.config.revenue_verified ? "success" : "warning"}>
          {data?.youtube.config.revenue_verified ? "YouTube revenue verified" : "YouTube revenue unverified"}
        </Badge>
        <span className="text-muted-foreground">
          Writing and video output stops at a human publication approval gate; nothing publishes itself.
        </span>
      </div>

      <GuardianStatGrid
        items={[
          { label: "Creator identities", value: String(data?.creator_manifest.count ?? 0) },
          { label: "Writing opportunities", value: String(data?.writing.opportunities ?? 0) },
          { label: "Writing queue", value: String(data?.writing.queue.items ?? 0) },
          { label: "Media content items", value: String(data?.media_farm.counts.content ?? 0) },
        ]}
      />

      <GuardianPanel
        title="Creator pipeline"
        hint="Where work currently sits between research and publication"
      >
        {data && data.pipeline.length > 0 ? (
          <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.pipeline.map((stage, index) => (
              <li key={stage.stage} className="border border-border/60 p-3">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-xs uppercase tracking-[0.12em] text-muted-foreground">{stage.stage}</span>
                  <span className="font-mono-ui text-lg">{stage.count}</span>
                </div>
                <div className="mt-1 text-[11px] text-muted-foreground">
                  {index + 1}. {stage.detail}
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <GuardianEmpty>No pipeline data available.</GuardianEmpty>
        )}
      </GuardianPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel title="Creator identities" hint="Declared AI creator personas and their status" source={data?.creator_manifest.source}>
          {data && data.creator_manifest.creators.length > 0 ? (
            <GuardianTable head={["Creator", "Niche", "Status", "Target", "Monetization"]}>
              {data.creator_manifest.creators.map((creator, index) => (
                <GuardianTr key={String(creator.id ?? index)}>
                  <GuardianTd>
                    <div className="font-mono-ui text-xs">{cell(creator, ["id"])}</div>
                    <div className="text-[11px] text-muted-foreground">{cell(creator, ["type"])}</div>
                  </GuardianTd>
                  <GuardianTd className="text-xs">{cell(creator, ["niche"])}</GuardianTd>
                  <GuardianTd>
                    <Badge tone={String(creator.status ?? "").includes("ready") ? "success" : "outline"}>
                      {cell(creator, ["status"])}
                    </Badge>
                  </GuardianTd>
                  <GuardianTd className="font-mono-ui text-xs">{cell(creator, ["content_target"])}</GuardianTd>
                  <GuardianTd className="text-[11px] text-muted-foreground">{cell(creator, ["monetization"])}</GuardianTd>
                </GuardianTr>
              ))}
            </GuardianTable>
          ) : (
            <GuardianEmpty>No creator manifest found.</GuardianEmpty>
          )}
        </GuardianPanel>

        <GuardianPanel title="Social creator mesh" hint={cell(meshCampaign ?? {}, ["objective"])} source={meshCampaign}>
          {meshCampaign && cell(meshCampaign, ["title"]) !== "-" ? (
            <div className="flex flex-col gap-3">
              <div>
                <div className="text-sm">{cell(meshCampaign, ["title"])}</div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  <Badge tone={cell(meshCampaign, ["status"]).includes("ready") ? "success" : "outline"}>
                    {cell(meshCampaign, ["status"])}
                  </Badge>
                  {Array.isArray(meshCampaign.platforms) &&
                    meshCampaign.platforms.map((platform) => (
                      <Badge key={String(platform)} tone="outline">
                        {String(platform)}
                      </Badge>
                    ))}
                </div>
              </div>
              <div className="text-[11px] text-muted-foreground">
                Cadence {cell(meshCampaign, ["cadence"])} · Budget {cell(meshCampaign, ["budget"])} ·{" "}
                {cell(meshCampaign, ["start_date"])} to {cell(meshCampaign, ["end_date"])}
              </div>
              {data && data.social_mesh.demand_signals.signals.length > 0 && (
                <ul className="flex flex-col gap-2 border-t border-border/40 pt-3 text-xs">
                  {data.social_mesh.demand_signals.signals.map((signal, index) => (
                    <li key={String(signal.topic ?? index)}>
                      <span className="font-mono-ui text-[11px] text-muted-foreground">
                        {cell(signal, ["topic"])}:
                      </span>{" "}
                      {cell(signal, ["fact"])}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <GuardianEmpty>No social mesh campaign found.</GuardianEmpty>
          )}
        </GuardianPanel>
      </div>

      <GuardianPanel
        title="Writing revenue"
        hint="News-driven opportunities scored before any drafting begins"
        source={data?.writing.source}
      >
        {data && data.writing.top.length > 0 ? (
          <GuardianTable head={["Topic", "Score", "Status", "Channels"]}>
            {data.writing.top.map((item, index) => {
              const channels = Array.isArray(item.monetization_candidates) ? item.monetization_candidates : [];
              return (
                <GuardianTr key={String(item.id ?? index)}>
                  <GuardianTd>
                    <div className="text-sm">{cell(item, ["topic", "title"])}</div>
                    <div className="text-[11px] text-muted-foreground">{cell(item, ["original_angle"])}</div>
                  </GuardianTd>
                  <GuardianTd className="font-mono-ui text-xs">{cell(item, ["opportunity_score"])}</GuardianTd>
                  <GuardianTd>
                    <Badge tone="outline">{cell(item, ["status"])}</Badge>
                  </GuardianTd>
                  <GuardianTd className="text-[11px] text-muted-foreground">
                    {channels
                      .map((channel) => {
                        const row = channel as Record<string, unknown>;
                        return `${cell(row, ["channel"])} (${cell(row, ["status"])})`;
                      })
                      .join(" · ") || "-"}
                  </GuardianTd>
                </GuardianTr>
              );
            })}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No writing opportunities found. The news research pass has not run.</GuardianEmpty>
        )}
        <p className="mt-3 text-[11px] text-muted-foreground">
          Queue: {String(data?.writing.queue.items ?? 0)} drafts · status{" "}
          {String(data?.writing.queue.status ?? "unknown")} — every channel except owned SEO requires approval.
        </p>
      </GuardianPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel title="YouTube studio" hint="Cadence and last daily run" source={data?.youtube.config.source}>
          <GuardianStatGrid
            items={[
              { label: "Config status", value: String(data?.youtube.config.status ?? "-") },
              { label: "Cadence", value: String(data?.youtube.config.cadence ?? "-") },
              { label: "External publish", value: String(data?.youtube.config.external_publish ?? "-") },
              { label: "Last run", value: formatWhen(data?.youtube.last_run.run_date) },
            ]}
          />
        </GuardianPanel>

        <GuardianPanel
          title="Media farm"
          hint={
            mediaCounts.length > 0
              ? mediaCounts.map(([table, count]) => `${count} ${table}`).join(" · ")
              : "Campaigns, content, influencers and tracked conversions"
          }
          source={data?.media_farm}
        >
          {data && data.media_farm.recent_content.length > 0 ? (
            <GuardianTable head={["Content", "Type", "Status", "Updated"]}>
              {data.media_farm.recent_content.map((item, index) => (
                <GuardianTr key={`${item.title}-${index}`}>
                  <GuardianTd className="text-xs">{item.title}</GuardianTd>
                  <GuardianTd className="text-xs text-muted-foreground">{item.content_type}</GuardianTd>
                  <GuardianTd>
                    <Badge tone={item.status === "published" ? "success" : "outline"}>{item.status}</Badge>
                  </GuardianTd>
                  <GuardianTd className="text-xs text-muted-foreground">{formatWhen(item.updated_at)}</GuardianTd>
                </GuardianTr>
              ))}
            </GuardianTable>
          ) : (
            <GuardianEmpty>
              {data?.media_farm.available
                ? "Media farm database is empty — no campaigns or content yet."
                : "No media farm database found."}
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
          <GuardianEmpty>No creator cron jobs matched.</GuardianEmpty>
        )}
      </GuardianPanel>
    </div>
  );
}
