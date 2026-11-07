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

export default function GuardianCommercialPage() {
  const { setAfterTitle } = usePageHeader();
  const { data, error, loading, refresh } = useGuardianSurface(() => api.guardianCommercial());

  useEffect(() => {
    setAfterTitle(
      <div className="flex flex-wrap items-center gap-2">
        <GuardianSurfaceNav active="/guardian/revenue" />
        <GuardianRefreshButton loading={loading} onClick={() => void refresh()} />
      </div>,
    );
    return () => setAfterTitle(null);
  }, [loading, refresh, setAfterTitle]);

  const statusCounts = Object.entries(data?.crm.by_status ?? {});

  return (
    <div className="flex flex-col gap-6">
      <GuardianPageError what="Guardian commercial" error={error} onRetry={() => void refresh()} />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone={data?.revenue_root.configured ? "success" : "warning"}>
          {data?.revenue_root.configured ? "Revenue root found" : "Revenue root missing"}
        </Badge>
        <span className="break-all font-mono-ui text-[11px] text-muted-foreground">
          {data?.revenue_root.path ?? "Set guardian.revenue_root in config.yaml"}
        </span>
      </div>

      <GuardianStatGrid
        items={[
          { label: "CRM contacts", value: String(data?.crm.contact_count ?? 0) },
          { label: "Campaign targets", value: String(data?.campaigns.targets.length ?? 0) },
          { label: "Queued work items", value: String(data?.lead_queue.total ?? 0) },
          {
            label: "Lead assets present",
            value: `${String((data?.lead_assets ?? []).filter((asset) => asset.exists).length)} / ${String((data?.lead_assets ?? []).length)}`,
          },
        ]}
      />

      <GuardianPanel
        title="CRM pipeline"
        hint={
          statusCounts.length > 0
            ? statusCounts.map(([status, count]) => `${count} ${status}`).join(" · ")
            : "Contact status distribution"
        }
        source={data?.crm.source}
      >
        {data && data.crm.contacts.length > 0 ? (
          <GuardianTable head={["Contact", "Company", "Source", "Status", "Score", "Updated"]}>
            {data.crm.contacts.map((contact, index) => (
              <GuardianTr key={String(contact.id ?? index)}>
                <GuardianTd>
                  <div className="text-sm">{cell(contact, ["contact", "name"])}</div>
                  <div className="font-mono-ui text-[11px] text-muted-foreground">{cell(contact, ["id"])}</div>
                </GuardianTd>
                <GuardianTd className="text-xs">{cell(contact, ["company"])}</GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{cell(contact, ["source"])}</GuardianTd>
                <GuardianTd>
                  <Badge tone={cell(contact, ["status"]) === "won" ? "success" : "outline"}>
                    {cell(contact, ["status"])}
                  </Badge>
                </GuardianTd>
                <GuardianTd className="font-mono-ui text-xs">
                  {cell(contact, ["score"])} <span className="text-muted-foreground">({cell(contact, ["fit"])})</span>
                </GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{formatWhen(cell(contact, ["updated_at"]))}</GuardianTd>
              </GuardianTr>
            ))}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No CRM contacts found.</GuardianEmpty>
        )}
      </GuardianPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel title="Lead assets" hint="Lead-generation properties in the revenue checkout">
          {data && data.lead_assets.length > 0 ? (
            <GuardianTable head={["Property", "Files", "Deploy markers", "Updated"]}>
              {data.lead_assets.map((asset) => (
                <GuardianTr key={asset.key}>
                  <GuardianTd>
                    <div className="text-sm">{asset.label}</div>
                    <div className="font-mono-ui text-[11px] text-muted-foreground">{asset.key}</div>
                  </GuardianTd>
                  <GuardianTd className="font-mono-ui text-xs">
                    {asset.exists ? asset.files.toLocaleString() : "missing"}
                  </GuardianTd>
                  <GuardianTd className="text-xs">
                    <div className="flex flex-wrap gap-1">
                      {asset.has_public && <Badge tone="success">public/</Badge>}
                      {asset.has_netlify && <Badge tone="outline">.netlify</Badge>}
                      {!asset.has_public && !asset.has_netlify && <span className="text-muted-foreground">-</span>}
                    </div>
                  </GuardianTd>
                  <GuardianTd className="text-xs text-muted-foreground">{formatWhen(asset.updated_at)}</GuardianTd>
                </GuardianTr>
              ))}
            </GuardianTable>
          ) : (
            <GuardianEmpty>Revenue checkout not found.</GuardianEmpty>
          )}
        </GuardianPanel>

        <GuardianPanel
          title="Campaign targets"
          hint="Offers needing configuration before a campaign can run"
          source={data?.campaigns.source}
        >
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
            <GuardianEmpty>No activation manifest found.</GuardianEmpty>
          )}
        </GuardianPanel>
      </div>

      <GuardianPanel title="Work queue" hint="Operator and agent tasks waiting to run" source={data?.lead_queue.source}>
        {data && data.lead_queue.items.length > 0 ? (
          <GuardianTable head={["ID", "Priority", "Status", "Description", "Owner"]}>
            {data.lead_queue.items.map((item, index) => (
              <GuardianTr key={String(item.id ?? index)}>
                <GuardianTd className="font-mono-ui text-[11px]">{cell(item, ["id"])}</GuardianTd>
                <GuardianTd className="text-xs">{cell(item, ["priority"])}</GuardianTd>
                <GuardianTd>
                  <Badge tone={cell(item, ["status"]) === "done" ? "success" : "outline"}>{cell(item, ["status"])}</Badge>
                </GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{cell(item, ["description", "title"])}</GuardianTd>
                <GuardianTd className="text-xs text-muted-foreground">{cell(item, ["owner"])}</GuardianTd>
              </GuardianTr>
            ))}
          </GuardianTable>
        ) : (
          <GuardianEmpty>No work queue found.</GuardianEmpty>
        )}
      </GuardianPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel title="Bond lead delivery" hint="Outbound transport for the UK/AU bond campaign" source={data?.bond_delivery.source}>
          {data?.bond_delivery.campaign ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
              {[
                ["Campaign", data.bond_delivery.campaign],
                ["Method", data.bond_delivery.delivery_method],
                ["Status", data.bond_delivery.status],
                ["Transport", data.bond_delivery.transport_status],
                ["Sender verification", data.bond_delivery.sender_verification_status],
                ["API dependency", data.bond_delivery.api_dependency === null ? null : String(data.bond_delivery.api_dependency)],
              ].map(([label, value]) => (
                <div key={String(label)} className="contents">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd>{value ?? "-"}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <GuardianEmpty>No bond delivery configuration found.</GuardianEmpty>
          )}
        </GuardianPanel>

        <GuardianPanel title="Credentials" hint="Presence only — values are never returned to the browser">
          <ul className="flex flex-col gap-1.5 font-mono-ui text-xs">
            {(data?.credentials ?? []).map((credential) => (
              <li key={credential.name} className="flex items-center justify-between gap-3 border-b border-border/40 pb-1.5 last:border-0">
                <span>{credential.name}</span>
                <Badge tone={credential.present ? "success" : "warning"}>{credential.present ? "present" : "missing"}</Badge>
              </li>
            ))}
            {(!data || data.credentials.length === 0) && <GuardianEmpty>No credential checks configured.</GuardianEmpty>}
          </ul>
        </GuardianPanel>
      </div>

      {data && data.leadengine.modules.length > 0 && (
        <GuardianPanel title="Lead engine modules" hint="Reusable qualification, dedup, CRM and delivery code">
          <div className="flex flex-wrap gap-1.5">
            {data.leadengine.modules.map((module) => (
              <Badge key={module} tone="outline">
                {module}
              </Badge>
            ))}
          </div>
        </GuardianPanel>
      )}

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
          <GuardianEmpty>No commercial cron jobs matched.</GuardianEmpty>
        )}
      </GuardianPanel>
    </div>
  );
}
