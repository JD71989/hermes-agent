import { useCallback, useEffect, useState } from "react";
import { Database, HardDrive, ShieldCheck } from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { api, type GuardianDatabaseHealth, type GuardianStorageSurface } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";
import { formatBytes } from "@/lib/guardian";

const LEVEL_TONE: Record<string, "success" | "warning" | "destructive" | "outline"> = {
  normal: "success",
  warning: "warning",
  high_alert: "warning",
  critical: "destructive",
  emergency: "destructive",
  unknown: "outline",
};

/**
 * Storage ledger for the System page. Reads the same capacity/location catalog
 * the `hermes guardian` verification uses. The database integrity sweep is a
 * separate, operator-triggered action: it runs `PRAGMA integrity_check` across
 * every database and legitimately takes minutes on a large home, so it never
 * runs on page load.
 */
export function GuardianStorageCard() {
  const [storage, setStorage] = useState<GuardianStorageSurface | null>(null);
  const [storageError, setStorageError] = useState<string | null>(null);
  const [loadingStorage, setLoadingStorage] = useState(true);
  const [health, setHealth] = useState<GuardianDatabaseHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

  const fetchStorage = useCallback(async () => {
    try {
      setStorage(await api.guardianStorage());
      setStorageError(null);
    } catch (err) {
      setStorageError(errorMessage(err));
    } finally {
      setLoadingStorage(false);
    }
  }, []);

  // Only an explicit rescan shows the spinner; the mount load must not set
  // state synchronously inside the effect.
  const rescan = useCallback(async () => {
    setLoadingStorage(true);
    await fetchStorage();
  }, [fetchStorage]);

  useEffect(() => {
    // `fetchStorage` only touches state after the request resolves, so this
    // mount load cannot cascade a render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchStorage();
  }, [fetchStorage]);

  const verifyDatabases = async () => {
    setVerifying(true);
    setHealthError(null);
    try {
      setHealth(await api.guardianDatabaseHealth(true));
    } catch (err) {
      setHealthError(errorMessage(err));
    } finally {
      setVerifying(false);
    }
  };

  const capacity = storage?.capacity;
  const categories = Object.entries(storage?.category_sizes ?? {}).sort((a, b) => b[1] - a[1]);
  const categoryTotal = categories.reduce((sum, [, size]) => sum + size, 0);
  const locations = [...(storage?.locations ?? [])].sort((a, b) => b.size_bytes - a.size_bytes);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <HardDrive className="h-5 w-5 text-muted-foreground" />
            <CardTitle className="text-base">Storage ledger</CardTitle>
            {capacity && <Badge tone={LEVEL_TONE[capacity.level] ?? "outline"}>{capacity.level.replace(/_/g, " ")}</Badge>}
          </div>
          <Button size="sm" outlined onClick={() => void rescan()} disabled={loadingStorage}>
            {loadingStorage ? <Spinner /> : "Rescan"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {storageError && (
          <p className="text-xs text-destructive">Storage check failed: {storageError}</p>
        )}

        {capacity && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: "Free", value: `${capacity.free_gb.toFixed(1)} GB` },
              { label: "Total", value: `${capacity.total_gb.toFixed(1)} GB` },
              { label: "Used", value: `${capacity.used_percent.toFixed(1)}%` },
              {
                label: "Hermes home",
                // The fast path skips the recursive walk; 0 means "not measured",
                // not "empty".
                value: capacity.hermes_size_gb > 0 ? `${capacity.hermes_size_gb.toFixed(2)} GB` : "not measured",
              },
            ].map((item) => (
              <div key={item.label} className="border border-border/60 p-3">
                <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{item.label}</div>
                <div className="mt-1 font-mono-ui text-base">{item.value}</div>
              </div>
            ))}
          </div>
        )}

        {categories.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {categories.map(([category, size]) => (
              <div key={category} className="flex items-center gap-3 text-xs">
                <span className="w-24 shrink-0 text-muted-foreground">{category}</span>
                <div className="h-1.5 flex-1 bg-secondary">
                  <div
                    className="h-full bg-midground/70"
                    style={{ width: `${categoryTotal > 0 ? Math.max(2, (size / categoryTotal) * 100) : 0}%` }}
                  />
                </div>
                <span className="w-20 shrink-0 text-right font-mono-ui">{formatBytes(size)}</span>
              </div>
            ))}
          </div>
        )}

        {locations.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full font-mondwest normal-case text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-muted-foreground">
                  <th className="py-2 pr-4 text-left font-medium">Location</th>
                  <th className="py-2 px-4 text-left font-medium">Category</th>
                  <th className="py-2 px-4 text-right font-medium">Size</th>
                  <th className="py-2 pl-4 text-left font-medium">State</th>
                </tr>
              </thead>
              <tbody>
                {locations.map((location) => (
                  <tr key={location.name} className="border-b border-border/50">
                    <td className="py-2 pr-4">
                      <div className="text-xs">{location.name}</div>
                      <div className="break-all font-mono-ui text-[11px] text-muted-foreground">{location.path}</div>
                    </td>
                    <td className="px-4 py-2 text-xs text-muted-foreground">{location.category}</td>
                    <td className="px-4 py-2 text-right font-mono-ui text-xs">
                      {location.exists ? formatBytes(location.size_bytes) : "-"}
                    </td>
                    <td className="py-2 pl-4">
                      {location.failure && location.failure !== "none" ? (
                        <Badge tone="destructive">{location.failure.replace(/_/g, " ")}</Badge>
                      ) : location.exists ? (
                        <Badge tone={location.writable ? "success" : "warning"}>
                          {location.writable ? "writable" : "read only"}
                        </Badge>
                      ) : (
                        <Badge tone="outline">missing</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex flex-col gap-2 border-t border-border/40 pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Database className="h-3.5 w-3.5" />
              Database integrity
              {health && (
                <Badge tone={health.invalid === 0 ? "success" : "destructive"}>
                  {health.invalid === 0 ? `${health.count} ok` : `${health.invalid} invalid`}
                </Badge>
              )}
            </div>
            <Button size="sm" outlined onClick={() => void verifyDatabases()} disabled={verifying}>
              {verifying ? (
                <>
                  <Spinner /> <span className="ml-2">Checking…</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="mr-2 h-3.5 w-3.5" /> Verify databases
                </>
              )}
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Runs <code>PRAGMA integrity_check</code> across every database in the Hermes home. This is thorough and can
            take minutes on a large home, so it runs only when you ask. Results are cached for 15 minutes.
          </p>
          {healthError && <p className="text-xs text-destructive">Integrity check failed: {healthError}</p>}
          {health && health.invalid > 0 && (
            <ul className="flex flex-col gap-1 text-xs">
              {health.databases
                .filter((row) => !row.valid)
                .map((row) => (
                  <li key={row.path} className="break-all">
                    <span className="text-destructive">{row.path}</span>
                    <span className="text-muted-foreground"> — {row.error ?? "failed integrity check"}</span>
                  </li>
                ))}
            </ul>
          )}
          {health && health.invalid === 0 && (
            <p className="text-[11px] text-muted-foreground">
              Last checked {new Date(health.generated_at).toLocaleString()}.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
