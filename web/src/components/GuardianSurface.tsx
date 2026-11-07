import type { ReactNode } from "react";
import { NavLink } from "react-router";
import { RefreshCw } from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Stats } from "@nous-research/ui/ui/components/stats";
import type { GuardianSource } from "@/lib/api";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";
import { GUARDIAN_SURFACES, formatWhen, sourceLabel, type GuardianSurfaceKey } from "@/lib/guardian";
import { LoadErrorNotice } from "@/components/LoadErrorNotice";

export function GuardianSurfaceNav({ active }: { active: GuardianSurfaceKey }) {
  return (
    <nav aria-label="Guardian surfaces" className="flex flex-wrap items-center gap-1.5">
      {GUARDIAN_SURFACES.map((surface) => (
        <NavLink
          key={surface.path}
          to={surface.path}
          end={surface.path === "/guardian"}
          className={cn(
            "px-3 py-1.5 text-xs font-sans uppercase tracking-[0.12em] transition-colors",
            "border border-border/60",
            surface.path === active
              ? "bg-secondary text-midground"
              : "text-text-secondary hover:text-midground hover:border-border",
          )}
        >
          {surface.label}
        </NavLink>
      ))}
    </nav>
  );
}

/**
 * A store's provenance. Guardian surfaces are projections over files and
 * SQLite stores that may not exist on this machine, so every panel states
 * whether its data was read, rather than rendering an empty list as "all clear".
 */
export function GuardianSourceBadge({ source, label }: { source: GuardianSource | undefined; label?: string }) {
  if (!source) return <Badge tone="outline">{sourceLabel(source, label)}</Badge>;
  const tone = source.available ? "success" : source.configured ? "warning" : "outline";
  return (
    <span className="inline-flex items-center gap-2">
      <Badge tone={tone}>{sourceLabel(source, label)}</Badge>
      {source.updated_at && (
        <span className="text-[11px] text-muted-foreground">updated {formatWhen(source.updated_at)}</span>
      )}
    </span>
  );
}

export function GuardianPanel({
  title,
  hint,
  source,
  actions,
  children,
  className,
}: {
  title: string;
  hint?: ReactNode;
  source?: GuardianSource;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("flex flex-col", className)}>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="min-w-0">
          <CardTitle className="text-base">{title}</CardTitle>
          {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          {source && <GuardianSourceBadge source={source} />}
          {actions}
        </div>
      </CardHeader>
      <CardContent className="flex-1">{children}</CardContent>
    </Card>
  );
}

export function GuardianEmpty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-xs text-muted-foreground">{children}</p>;
}

export function GuardianStatGrid({ items }: { items: Array<{ label: string; value: ReactNode }> }) {
  const stats = items.map((item) => ({
    label: item.label,
    value: typeof item.value === "string" ? item.value : { key: item.label, node: item.value },
  }));
  return <Stats items={stats} />;
}

export function GuardianTable({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full font-mondwest normal-case text-sm">
        <thead>
          <tr className="border-b border-border text-xs text-muted-foreground">
            {head.map((label, index) => (
              <th
                key={`${label}-${index}`}
                className={cn("py-2 font-medium", index === 0 ? "text-left pr-4" : "text-left px-4 last:pl-4 last:pr-0")}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function GuardianTr({ children }: { children: ReactNode }) {
  return <tr className="border-b border-border/50 transition-colors hover:bg-secondary/20">{children}</tr>;
}

export function GuardianTd({ children, className }: { children: ReactNode; className?: string }) {
  return <td className={cn("py-2 pr-4 align-top", className)}>{children}</td>;
}

export function GuardianRefreshButton({ loading, onClick }: { loading: boolean; onClick: () => void }) {
  const { t } = useI18n();
  return (
    <Button
      type="button"
      ghost
      size="icon"
      className="text-muted-foreground hover:text-foreground"
      onClick={onClick}
      disabled={loading}
      aria-label={t.common.refresh}
    >
      {loading ? <Spinner /> : <RefreshCw />}
    </Button>
  );
}

export function GuardianPageError({
  what,
  error,
  onRetry,
}: {
  what: string;
  error: string | null;
  onRetry: () => void;
}) {
  if (!error) return null;
  return <LoadErrorNotice what={what} detail={error} onRetry={onRetry} />;
}
