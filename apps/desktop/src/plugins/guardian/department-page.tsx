/**
 * The desktop Guardian department page: one component renders any of the nine
 * departments from the read-only `/api/guardian/*` payloads. Read-only by
 * design — the stores these surfaces project are written by Hermes jobs, not by
 * this page.
 */

import { host } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useState } from 'react'

import { hermesApi } from '@/hermes'

import {
  departmentById,
  describe,
  GUARDIAN_DEPARTMENTS,
  type GuardianBlock,
  type GuardianDepartmentId,
  type GuardianPayload
} from './departments'

const POLL_MS = 60_000

function Block({ block }: { block: GuardianBlock }) {
  if (block.kind === 'stats') {
    return (
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {block.items.map(item => (
          <div
            key={item.label}
            className="rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-quinary) px-3 py-2"
          >
            <div className="text-[0.65rem] uppercase tracking-[0.12em] text-(--ui-text-tertiary)">{item.label}</div>
            <div className="mt-1 font-mono text-[0.95rem] tabular-nums text-foreground">{item.value}</div>
          </div>
        ))}
      </div>
    )
  }

  if (block.kind === 'list') {
    return (
      <section className="rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-quinary)">
        <header className="border-b border-(--ui-stroke-tertiary) px-3 py-2">
          <h2 className="text-[0.8rem] font-medium text-foreground">{block.title}</h2>
          {block.hint && <p className="mt-0.5 text-[0.68rem] text-(--ui-text-tertiary)">{block.hint}</p>}
        </header>
        <ul className="divide-y divide-(--ui-stroke-tertiary)">
          {block.items.map((item, index) => (
            <li key={`${item}-${index}`} className="px-3 py-1.5 text-[0.75rem] text-(--ui-text-secondary)">
              {item}
            </li>
          ))}
          {block.items.length === 0 && (
            <li className="px-3 py-2 text-[0.75rem] text-(--ui-text-tertiary)">Nothing recorded.</li>
          )}
        </ul>
      </section>
    )
  }

  return (
    <section className="rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-quinary)">
      <header className="border-b border-(--ui-stroke-tertiary) px-3 py-2">
        <h2 className="text-[0.8rem] font-medium text-foreground">{block.title}</h2>
        {block.hint && <p className="mt-0.5 text-[0.68rem] text-(--ui-text-tertiary)">{block.hint}</p>}
      </header>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[0.72rem]">
          <thead>
            <tr className="text-(--ui-text-tertiary)">
              {block.columns.map(column => (
                <th key={column} className="whitespace-nowrap px-3 py-1.5 font-normal uppercase tracking-[0.08em]">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-(--ui-stroke-tertiary)">
            {block.rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="align-top">
                {row.map((cell, cellIndex) => (
                  <td
                    key={cellIndex}
                    className={
                      cellIndex === 0
                        ? 'px-3 py-1.5 text-foreground'
                        : 'px-3 py-1.5 text-(--ui-text-secondary)'
                    }
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
            {block.rows.length === 0 && (
              <tr>
                <td className="px-3 py-2 text-(--ui-text-tertiary)" colSpan={block.columns.length}>
                  Nothing recorded.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function GuardianDepartmentPage({ id }: { id: GuardianDepartmentId }) {
  const department = departmentById(id)
  const [payload, setPayload] = useState<GuardianPayload | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const next = await hermesApi<GuardianPayload>({ path: department.endpoint })
      setPayload(next)
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setLoading(false)
    }
  }, [department.endpoint])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), POLL_MS)
    return () => window.clearInterval(timer)
  }, [load])

  const blocks = payload ? describe(id, payload) : []

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[0.65rem] uppercase tracking-[0.16em] text-(--ui-text-tertiary)">Guardian</span>
            <span className="text-(--ui-text-tertiary)">/</span>
            <h1 className="text-[length:var(--conversation-text-font-size)] font-semibold text-foreground">
              {department.name}
            </h1>
          </div>
          <p className="mt-1 max-w-3xl text-[0.75rem] text-(--ui-text-secondary)">{department.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="rounded-md border border-(--ui-stroke-tertiary) px-2.5 py-1 text-[0.7rem] text-(--ui-text-secondary) hover:bg-(--chrome-action-hover) hover:text-foreground"
            onClick={() => void load()}
            type="button"
          >
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      <nav aria-label="Guardian departments" className="flex flex-wrap gap-1">
        <button
          className="rounded-md border border-(--ui-stroke-tertiary) px-2 py-1 text-[0.68rem] text-(--ui-text-tertiary) hover:text-foreground"
          onClick={() => host.navigate('/guardian')}
          type="button"
        >
          Command Centre
        </button>
        {GUARDIAN_DEPARTMENTS.map(entry => (
          <button
            key={entry.id}
            className={
              entry.id === id
                ? 'rounded-md border border-(--ui-stroke-primary) bg-(--ui-bg-tertiary) px-2 py-1 text-[0.68rem] text-foreground'
                : 'rounded-md border border-(--ui-stroke-tertiary) px-2 py-1 text-[0.68rem] text-(--ui-text-tertiary) hover:text-foreground'
            }
            onClick={() => host.navigate(entry.path)}
            type="button"
          >
            {entry.name}
          </button>
        ))}
      </nav>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-[0.75rem] text-destructive">
          {error}
        </div>
      )}

      {!payload && loading && <div className="text-[0.75rem] text-(--ui-text-tertiary)">Loading {department.name}…</div>}

      {blocks.map((block, index) => (
        <Block key={`${block.kind}-${index}`} block={block} />
      ))}

      <footer className="text-[0.68rem] text-(--ui-text-tertiary)">
        Read-only projection over existing Hermes stores. Live trading, withdrawals and leverage stay disabled unless
        separately authorised.
      </footer>
    </div>
  )
}
