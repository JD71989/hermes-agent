/**
 * Guardian hub — the single desktop entry point for the nine departments.
 *
 * Each card carries a live headline pulled from the same read-only
 * `/api/guardian/*` projections the department pages render. Counts are shown
 * only when the underlying store answered; a missing store reads as "—", never
 * as zero revenue.
 */

import { host } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useState } from 'react'

import { hermesApi } from '@/hermes'

import {
  GUARDIAN_DEPARTMENTS,
  headline,
  type GuardianDepartmentId,
  type GuardianPayload
} from './departments'

const POLL_MS = 60_000

type Headlines = Partial<Record<GuardianDepartmentId, string>>

export function GuardianHubPage() {
  const [headlines, setHeadlines] = useState<Headlines>({})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    const results = await Promise.allSettled(
      GUARDIAN_DEPARTMENTS.map(department =>
        hermesApi<GuardianPayload>({ path: department.endpoint }).then(payload => ({ id: department.id, payload }))
      )
    )

    const next: Headlines = {}
    let firstError = ''

    for (const result of results) {
      if (result.status === 'fulfilled') {
        next[result.value.id] = headline(result.value.id, result.value.payload)
      } else if (!firstError) {
        firstError =
          result.reason instanceof Error ? result.reason.message : String(result.reason ?? 'Guardian backend unavailable')
      }
    }

    setHeadlines(next)
    setError(firstError)
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), POLL_MS)
    return () => window.clearInterval(timer)
  }, [load])

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[0.65rem] uppercase tracking-[0.16em] text-(--ui-text-tertiary)">
              Hermes departments
            </span>
            <h1 className="text-[length:var(--conversation-text-font-size)] font-semibold text-foreground">
              Guardian Command Centre
            </h1>
          </div>
          <p className="mt-1 max-w-3xl text-[0.75rem] text-(--ui-text-secondary)">
            Guardian V5 capabilities folded into Hermes: one control centre, nine departments, no separate application.
            Every surface is a read-only projection over stores Hermes already runs.
          </p>
        </div>
        <button
          className="rounded-md border border-(--ui-stroke-tertiary) px-2.5 py-1 text-[0.7rem] text-(--ui-text-secondary) hover:bg-(--chrome-action-hover) hover:text-foreground"
          onClick={() => void load()}
          type="button"
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </header>

      <div className="flex flex-wrap gap-1.5 text-[0.68rem]">
        <span className="rounded-md border border-(--ui-stroke-tertiary) px-2 py-1 text-(--ui-text-secondary)">
          Paper &amp; research only
        </span>
        <span className="rounded-md border border-(--ui-stroke-tertiary) px-2 py-1 text-(--ui-text-secondary)">
          Live trading, withdrawals &amp; leverage disabled
        </span>
        <span className="rounded-md border border-(--ui-stroke-tertiary) px-2 py-1 text-(--ui-text-secondary)">
          CyberLab defensive only
        </span>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-[0.72rem] text-destructive">
          {error}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {GUARDIAN_DEPARTMENTS.map(department => (
          <button
            key={department.id}
            className="flex flex-col gap-2 rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-quinary) p-3 text-left transition-colors hover:border-(--ui-stroke-primary) hover:bg-(--ui-bg-tertiary)"
            onClick={() => host.navigate(department.path)}
            type="button"
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-[0.82rem] font-medium text-foreground">{department.name}</span>
              <span className="shrink-0 rounded border border-(--ui-stroke-tertiary) px-1.5 py-0.5 font-mono text-[0.65rem] text-(--ui-text-secondary)">
                {headlines[department.id] ?? '…'}
              </span>
            </div>
            <span className="text-[0.7rem] text-(--ui-text-tertiary)">{department.tagline}</span>
            <span className="mt-auto text-[0.68rem] text-(--ui-text-secondary)">Open department →</span>
          </button>
        ))}
      </div>

      <section className="rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-quinary) px-3 py-2 text-[0.7rem] text-(--ui-text-tertiary)">
        The browser dashboard renders the same departments at <span className="font-mono">/guardian</span> with full
        tables and source badges. Both surfaces read the same backend endpoints — there is no second database.
      </section>
    </div>
  )
}
