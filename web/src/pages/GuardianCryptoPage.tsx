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

export default function GuardianCryptoPage() {
  const { setAfterTitle } = usePageHeader();
  const { data, error, loading, refresh } = useGuardianSurface(() => api.guardianCrypto());

  useEffect(() => {
    setAfterTitle(
      <div className="flex flex-wrap items-center gap-2">
        <GuardianSurfaceNav active="/guardian/crypto" />
        <GuardianRefreshButton loading={loading} onClick={() => void refresh()} />
      </div>,
    );
    return () => setAfterTitle(null);
  }, [loading, refresh, setAfterTitle]);

  const demo = data?.detector.demo;

  return (
    <div className="flex flex-col gap-6">
      <GuardianPageError what="Guardian crypto" error={error} onRetry={() => void refresh()} />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone={data?.policy.live_trading_enabled ? "destructive" : "success"}>
          {data?.policy.live_trading_enabled ? "LIVE EXECUTION ENABLED" : "PAPER ONLY — LIVE GATED"}
        </Badge>
        <span className="text-muted-foreground">
          Solana-first launch detection, risk gating and paper-trade intelligence. No wallet movement.
        </span>
      </div>

      <GuardianStatGrid
        items={[
          { label: "Detector", value: data?.detector.status ?? "-" },
          { label: "Risk gate", value: data?.detector.risk_gate ?? "-" },
          { label: "Paper trading", value: data?.detector.paper_trading ?? "-" },
          { label: "Live execution", value: data?.detector.live_execution ?? "-" },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <GuardianPanel title="Signal stack" hint="Inputs supported by current Solana data providers">
          <ul className="flex flex-wrap gap-1.5">
            {(data?.detector.signal_stack ?? []).map((signal) => (
              <Badge key={signal} tone="outline">
                {signal}
              </Badge>
            ))}
            {(!data || data.detector.signal_stack.length === 0) && <GuardianEmpty>No signal stack configured.</GuardianEmpty>}
          </ul>
        </GuardianPanel>

        <GuardianPanel title="Research-backed gate" hint="Current evidence incorporated into scoring">
          {demo ? (
            <div className="flex flex-col gap-3 text-sm">
              <div className="flex items-center gap-2">
                <Badge tone={demo.decision === "REJECT" ? "destructive" : demo.decision === "PAPER" ? "success" : "outline"}>
                  {demo.decision}
                </Badge>
                <span className="text-muted-foreground">Demo score: {demo.score}/100</span>
                <span className="font-mono-ui text-xs text-muted-foreground">{demo.symbol}</span>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Hard failures are rejection conditions, not merely deductions. Bundler/insider/developer tags are first-class risk inputs.
                Paper trades are recorded before any live transaction path is enabled.
              </p>
              {demo.hard_fails.length > 0 && (
                <ul className="flex flex-wrap gap-1.5">
                  {demo.hard_fails.map((fail) => (
                    <Badge key={fail} tone="destructive">
                      {fail}
                    </Badge>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <GuardianEmpty>No demo assessment available.</GuardianEmpty>
          )}
        </GuardianPanel>
      </div>

      <GuardianPanel title="Execution policy" hint="No automatic wallet movement is enabled by this page">
        <p className="text-sm text-muted-foreground">
          A future executor must use an isolated trading wallet, fixed exposure limits, explicit transaction approval,
          MEV-aware routing, and verified exit/liquidity checks.
        </p>
      </GuardianPanel>

      <GuardianPanel title="Capabilities" hint="Crypto modules present on this install (names only for credentials)">
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
          <GuardianEmpty>No crypto cron jobs matched.</GuardianEmpty>
        )}
      </GuardianPanel>
    </div>
  );
}
