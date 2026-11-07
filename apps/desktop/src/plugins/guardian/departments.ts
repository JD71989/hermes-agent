/**
 * Guardian department specs + payload → view-model mapping.
 *
 * The Guardian surfaces are read-only projections served by the Hermes backend
 * at `/api/guardian/*` (see `hermes_cli/guardian_ops.py`). This module keeps the
 * desktop plugin declarative: one spec per department, one `describe()` that
 * turns a payload into stat / table / list blocks. No new data source.
 */

export type GuardianDepartmentId =
  | 'revenue'
  | 'marketing'
  | 'creators'
  | 'crypto'
  | 'trading'
  | 'intelligence'
  | 'cyberlab'
  | 'automation'
  | 'system'

export interface GuardianDepartment {
  id: GuardianDepartmentId
  path: string
  name: string
  tagline: string
  description: string
  endpoint: string
}

export const GUARDIAN_DEPARTMENTS: readonly GuardianDepartment[] = [
  {
    id: 'revenue',
    path: '/guardian/revenue',
    name: 'Business & Revenue',
    tagline: 'Portfolio, engines and verified evidence',
    description:
      'LEADGEN portfolio experiments, revenue fabric, evidence ledger and approvals. Verified revenue only — the ledger decides.',
    endpoint: '/api/guardian/revenue'
  },
  {
    id: 'marketing',
    path: '/guardian/marketing',
    name: 'Marketing',
    tagline: 'Traffic lanes, funnel and campaigns',
    description:
      'One traffic engine with controlled distribution lanes. Counts come from the CRM, writing queue, media farm and scored opportunity queue.',
    endpoint: '/api/guardian/marketing'
  },
  {
    id: 'creators',
    path: '/guardian/creators',
    name: 'Media & Creators',
    tagline: 'Creator identities, writing revenue and media farm',
    description:
      'AI creator identities, writing opportunities, publication gates and media-farm output. Human approval gates publication.',
    endpoint: '/api/guardian/creators'
  },
  {
    id: 'crypto',
    path: '/guardian/crypto',
    name: 'Crypto',
    tagline: 'Launch intelligence and a paper-only risk gate',
    description:
      'Solana-first token detection, risk gating and paper-trade scoring. Live execution and wallet movement stay disabled.',
    endpoint: '/api/guardian/crypto'
  },
  {
    id: 'trading',
    path: '/guardian/trading',
    name: 'Trading',
    tagline: 'Paper lanes and workflow evidence',
    description:
      'Pump.fun, Polymarket and Pionex research lanes. Paper only: execution, leverage and withdrawals remain locked.',
    endpoint: '/api/guardian/trading'
  },
  {
    id: 'intelligence',
    path: '/guardian/intelligence',
    name: 'Intelligence & Research',
    tagline: 'Scored opportunities and research artifacts',
    description:
      'Actionable opportunity queue, live targets, research files and workflow state. Nothing is reported that the evidence does not support.',
    endpoint: '/api/guardian/intelligence'
  },
  {
    id: 'cyberlab',
    path: '/guardian/cyberlab',
    name: 'CyberLab',
    tagline: 'Defensive research only',
    description:
      'Threat intelligence and hardening research with read-only health checks through existing Hermes task types. No offensive execution.',
    endpoint: '/api/guardian/cyberlab'
  },
  {
    id: 'automation',
    path: '/guardian/automation',
    name: 'Automation',
    tagline: 'Cron, workflows and approvals',
    description:
      'The existing Hermes scheduler and workflow engine. No second orchestrator — approvals surface the work that needs a human decision.',
    endpoint: '/api/guardian/automation'
  },
  {
    id: 'system',
    path: '/guardian/system',
    name: 'System Administration',
    tagline: 'Storage, health and native Hermes links',
    description:
      'Capacity, storage locations and cron health, with links to the Hermes pages that own config, keys, models and logs.',
    endpoint: '/api/guardian/system'
  }
] as const

export function departmentById(id: GuardianDepartmentId): GuardianDepartment {
  const found = GUARDIAN_DEPARTMENTS.find(department => department.id === id)
  if (!found) {
    throw new Error(`Unknown Guardian department: ${id}`)
  }
  return found
}

// ── payload helpers ─────────────────────────────────────────────────────────

export type GuardianPayload = Record<string, unknown>

type Row = Record<string, unknown>

function record(value: unknown): Row {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Row) : {}
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function text(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  return String(value)
}

function count(value: unknown): string {
  return typeof value === 'number' ? String(value) : '—'
}

function money(value: unknown): string {
  return typeof value === 'number' ? `$${value.toLocaleString()}` : '—'
}

function sourceLabel(value: unknown): string {
  const source = record(value)
  if (source.available === true) {
    return 'available'
  }
  return source.error ? `missing (${String(source.error)})` : 'missing'
}

function jobRows(value: unknown): string[][] {
  return list(record(value).jobs)
    .map(record)
    .slice(0, 12)
    .map(job => [
      text(job.name || job.id),
      text(job.schedule),
      job.enabled === false ? 'disabled' : text(job.last_status || 'pending'),
      text(job.last_run)
    ])
}

// ── view model ──────────────────────────────────────────────────────────────

export interface StatBlock {
  kind: 'stats'
  items: Array<{ label: string; value: string }>
}

export interface TableBlock {
  kind: 'table'
  title: string
  hint?: string
  columns: string[]
  rows: string[][]
}

export interface ListBlock {
  kind: 'list'
  title: string
  hint?: string
  items: string[]
}

export type GuardianBlock = StatBlock | TableBlock | ListBlock

const JOB_COLUMNS = ['Job', 'Schedule', 'Last status', 'Last run']

export function describe(id: GuardianDepartmentId, payload: GuardianPayload): GuardianBlock[] {
  switch (id) {
    case 'revenue':
      return describeRevenue(payload)
    case 'marketing':
      return describeMarketing(payload)
    case 'creators':
      return describeCreators(payload)
    case 'crypto':
      return describeCrypto(payload)
    case 'trading':
      return describeTrading(payload)
    case 'intelligence':
      return describeIntelligence(payload)
    case 'cyberlab':
      return describeCyberlab(payload)
    case 'automation':
      return describeAutomation(payload)
    case 'system':
      return describeSystem(payload)
  }
}

/** One short headline per department for the hub cards. */
export function headline(id: GuardianDepartmentId, payload: GuardianPayload): string {
  switch (id) {
    case 'revenue': {
      const counts = record(record(payload.portfolio).counts)
      return `${count(counts.total)} experiments`
    }
    case 'marketing':
      return `${count(record(payload.funnel).crm_contacts)} contacts`
    case 'creators':
      return `${count(record(payload.creator_manifest).count)} creators`
    case 'crypto':
      return text(record(record(payload.detector).demo).decision)
    case 'trading':
      return `${count(list(payload.lanes).length)} paper lanes`
    case 'intelligence':
      return `${count(list(record(record(payload.opportunity_intelligence).queue).items).length)} opportunities`
    case 'cyberlab':
      return text(record(payload.policy).mode)
    case 'automation':
      return `${count(list(record(payload.cron).jobs).length)} cron jobs`
    case 'system': {
      const used = record(record(payload.storage).capacity).used_percent
      return typeof used === 'number' ? `${used.toFixed(1)}% used` : 'no capacity'
    }
  }
}

function describeRevenue(payload: GuardianPayload): GuardianBlock[] {
  const portfolio = record(payload.portfolio)
  const counts = record(portfolio.counts)
  const evidence = record(payload.evidence)
  const approvals = record(payload.approvals)

  return [
    {
      kind: 'stats',
      items: [
        { label: 'Experiments', value: count(counts.total) },
        { label: 'Ready for review', value: count(counts.READY_FOR_REVIEW ?? 0) },
        { label: 'In progress', value: count(counts.IN_PROGRESS ?? 0) },
        { label: 'Pending approvals', value: count(approvals.pending) }
      ]
    },
    {
      kind: 'table',
      title: 'Portfolio experiments',
      hint: `Source: ${sourceLabel(portfolio.source)}`,
      columns: ['Experiment', 'State', 'Tier', 'Reason'],
      rows: list(portfolio.experiments)
        .map(record)
        .slice(0, 20)
        .map(experiment => [
          text(experiment.name || experiment.id),
          text(experiment.effective_state || experiment.state),
          text(experiment.tier),
          text(experiment.reason)
        ])
    },
    {
      kind: 'list',
      title: 'Verified revenue',
      hint: `Source: ${sourceLabel(evidence.source)}`,
      items: [
        `Ledger records: ${count(evidence.records)}`,
        `Verified leads: ${count(evidence.leads)}`,
        `Verified revenue: ${evidence.verified ? money(evidence.verified_revenue_usd) : '$0'}`,
        text(evidence.note)
      ]
    },
    {
      kind: 'table',
      title: 'Automation feeding revenue',
      columns: JOB_COLUMNS,
      rows: jobRows(payload.automation)
    }
  ]
}

function describeMarketing(payload: GuardianPayload): GuardianBlock[] {
  const funnel = record(payload.funnel)
  const campaigns = record(payload.campaigns)

  return [
    {
      kind: 'stats',
      items: [
        { label: 'Opportunities', value: count(funnel.opportunities) },
        { label: 'CRM contacts', value: count(funnel.crm_contacts) },
        { label: 'Writing opportunities', value: count(funnel.writing_opportunities) },
        { label: 'Campaign targets', value: count(funnel.campaign_targets) }
      ]
    },
    {
      kind: 'table',
      title: 'Traffic lanes',
      hint: 'Measured traffic only — no invented numbers',
      columns: ['Lane', 'Count', 'Description'],
      rows: list(payload.lanes)
        .map(record)
        .map(lane => [text(lane.lane), count(lane.count), text(lane.description)])
    },
    {
      kind: 'table',
      title: 'Campaign targets',
      hint: 'Offers that need configuration before a campaign can run',
      columns: ['Target', 'Status', 'Requires'],
      rows: list(campaigns.targets)
        .map(record)
        .map(target => [
          text(target.name),
          text(target.status),
          list(target.details_required).map(String).join(', ') || 'no listed blockers'
        ])
    },
    {
      kind: 'table',
      title: 'Automation feeding marketing',
      columns: JOB_COLUMNS,
      rows: jobRows(payload.automation)
    }
  ]
}

function describeCreators(payload: GuardianPayload): GuardianBlock[] {
  const manifest = record(payload.creator_manifest)
  const writing = record(payload.writing)
  const media = record(payload.media_farm)

  return [
    {
      kind: 'stats',
      items: [
        { label: 'Creator identities', value: count(manifest.count) },
        { label: 'Writing opportunities', value: count(writing.opportunities) },
        { label: 'Writing queue', value: count(record(writing.queue).items) },
        { label: 'Media content', value: count(record(media.counts).content) }
      ]
    },
    {
      kind: 'table',
      title: 'Pipeline',
      hint: 'Research → drafts → human publication approval',
      columns: ['Stage', 'Count', 'Detail'],
      rows: list(payload.pipeline)
        .map(record)
        .map(stage => [text(stage.stage), count(stage.count), text(stage.detail)])
    },
    {
      kind: 'table',
      title: 'Creator identities',
      hint: `Source: ${sourceLabel(manifest.source)}`,
      columns: ['Creator', 'Niche', 'Status', 'Monetisation'],
      rows: list(manifest.creators)
        .map(record)
        .slice(0, 12)
        .map(creator => [
          text(creator.id),
          text(creator.niche),
          text(creator.status),
          text(creator.monetization)
        ])
    },
    {
      kind: 'table',
      title: 'Top writing opportunities',
      hint: `Source: ${sourceLabel(writing.source)}`,
      columns: ['Topic', 'Score', 'Status'],
      rows: list(writing.top)
        .map(record)
        .slice(0, 10)
        .map(item => [text(item.topic), count(item.opportunity_score), text(item.status)])
    }
  ]
}

function describeCrypto(payload: GuardianPayload): GuardianBlock[] {
  const policy = record(payload.policy)
  const detector = record(payload.detector)
  const demo = record(detector.demo)
  const hardFails = list(demo.hard_fails).map(String)

  return [
    {
      kind: 'stats',
      items: [
        { label: 'Live trading', value: policy.live_trading_enabled === true ? 'ENABLED' : 'GATED' },
        { label: 'Detector', value: text(detector.status) },
        { label: 'Risk gate', value: text(detector.risk_gate) },
        { label: 'Demo decision', value: `${text(demo.decision)} (${count(demo.score)}/100)` }
      ]
    },
    {
      kind: 'list',
      title: 'Signal stack',
      hint: 'Inputs supported by the current data providers',
      items: list(detector.signal_stack).map(String)
    },
    {
      kind: 'list',
      title: 'Demo hard failures',
      hint: 'Rejection conditions, not deductions',
      items: hardFails.length > 0 ? hardFails : ['No hard failures on the demo candidate']
    },
    {
      kind: 'table',
      title: 'Capabilities',
      hint: 'Credential checks report names only',
      columns: ['Capability', 'Module', 'Credentials'],
      rows: list(payload.capabilities)
        .map(record)
        .map(capability => [
          text(capability.label),
          capability.present === true ? 'present' : 'missing',
          capability.credentials_present === true ? 'present' : 'missing'
        ])
    },
    {
      kind: 'table',
      title: 'Automation feeding crypto',
      columns: JOB_COLUMNS,
      rows: jobRows(payload.automation)
    }
  ]
}

function describeTrading(payload: GuardianPayload): GuardianBlock[] {
  const policy = record(payload.policy)
  const intelligence = record(payload.opportunity_intelligence)

  return [
    {
      kind: 'stats',
      items: [
        { label: 'Live trading', value: policy.live_trading_enabled === true ? 'ENABLED' : 'LOCKED' },
        { label: 'Paper lanes', value: count(list(payload.lanes).length) },
        { label: 'Scored opportunities', value: count(list(record(intelligence.queue).items).length) },
        { label: 'Workflows', value: count(list(payload.workflows).length) }
      ]
    },
    {
      kind: 'table',
      title: 'Trading lanes',
      hint: 'Paper only — no funds exposed',
      columns: ['Lane', 'Mode', 'Status'],
      rows: list(payload.lanes)
        .map(record)
        .map(lane => [text(lane.lane), text(lane.mode), text(lane.status)])
    },
    {
      kind: 'table',
      title: 'Scored opportunities',
      columns: ['Opportunity', 'Value', 'Fit', 'Eligibility'],
      rows: list(record(intelligence.queue).items)
        .map(record)
        .slice(0, 10)
        .map(item => [text(item.title || item.name), money(item.value_usd), text(item.fit), text(item.eligibility)])
    },
    {
      kind: 'table',
      title: 'Guardian workflows',
      columns: ['Workflow', 'Engine', 'State', 'Step'],
      rows: list(payload.workflows)
        .map(record)
        .slice(0, 12)
        .map(workflow => [text(workflow.name || workflow.id), text(workflow.engine), text(workflow.state), text(workflow.current_step)])
    },
    {
      kind: 'table',
      title: 'Automation feeding trading',
      columns: JOB_COLUMNS,
      rows: jobRows(payload.automation)
    }
  ]
}

function describeIntelligence(payload: GuardianPayload): GuardianBlock[] {
  const intelligence = record(payload.opportunity_intelligence)
  const queue = record(intelligence.queue)
  const research = record(payload.research)

  return [
    {
      kind: 'stats',
      items: [
        { label: 'Scored opportunities', value: count(list(queue.items).length) },
        { label: 'Verified revenue', value: money(queue.verified_revenue_usd) },
        { label: 'Research artifacts', value: count(list(research.artifacts).length) },
        { label: 'Workflows', value: count(list(payload.workflows).length) }
      ]
    },
    {
      kind: 'table',
      title: 'Actionable opportunities',
      hint: `Source: ${sourceLabel(queue.source)}`,
      columns: ['Opportunity', 'Value', 'Fit', 'Eligibility'],
      rows: list(queue.items)
        .map(record)
        .slice(0, 12)
        .map(item => [text(item.title), money(item.value_usd), text(item.fit), text(item.eligibility)])
    },
    {
      kind: 'table',
      title: 'Research artifacts',
      hint: `Source: ${sourceLabel(research.source)}`,
      columns: ['File', 'Kind', 'Updated'],
      rows: list(research.artifacts)
        .map(record)
        .slice(0, 12)
        .map(artifact => [text(artifact.name), text(artifact.kind), text(artifact.updated_at)])
    },
    {
      kind: 'table',
      title: 'Guardian workflows',
      columns: ['Workflow', 'Engine', 'State', 'Step'],
      rows: list(payload.workflows)
        .map(record)
        .slice(0, 12)
        .map(workflow => [text(workflow.name || workflow.id), text(workflow.engine), text(workflow.state), text(workflow.current_step)])
    },
    {
      kind: 'table',
      title: 'Automation feeding intelligence',
      columns: JOB_COLUMNS,
      rows: jobRows(payload.automation)
    }
  ]
}

function describeCyberlab(payload: GuardianPayload): GuardianBlock[] {
  const policy = record(payload.policy)
  const status = record(payload.status)
  const boundary = record(payload.boundary)
  const vault = record(payload.vault)
  const physical = record(payload.physical_security)

  return [
    {
      kind: 'stats',
      items: [
        { label: 'Mode', value: text(policy.mode) },
        { label: 'Offensive execution', value: policy.offensive_execution === true ? 'ENABLED' : 'FORBIDDEN' },
        { label: 'Vault posture', value: text(vault.status) },
        { label: 'Physical security', value: text(physical.status) }
      ]
    },
    {
      kind: 'list',
      title: 'Research state',
      hint: 'Honest empty states — no invented findings',
      items: Object.values(status).map(String)
    },
    {
      kind: 'list',
      title: 'Allowed',
      items: list(boundary.allowed).map(String)
    },
    {
      kind: 'list',
      title: 'Forbidden',
      items: list(boundary.forbidden).map(String)
    },
    {
      kind: 'table',
      title: 'Automation feeding CyberLab',
      columns: JOB_COLUMNS,
      rows: jobRows(payload.automation)
    }
  ]
}

function describeAutomation(payload: GuardianPayload): GuardianBlock[] {
  const approvals = record(payload.approvals)
  const workflows = list(payload.workflows).map(record)
  const running = workflows.filter(workflow => workflow.state === 'running').length

  return [
    {
      kind: 'stats',
      items: [
        { label: 'Cron jobs', value: count(list(record(payload.cron).jobs).length) },
        { label: 'Workflows running', value: String(running) },
        { label: 'Workflows', value: String(workflows.length) },
        { label: 'Pending approvals', value: count(approvals.pending) }
      ]
    },
    {
      kind: 'table',
      title: 'Guardian workflow controller',
      hint: 'Persistent multi-stage workflows backed by the Hermes execution ledger',
      columns: ['Workflow', 'Engine', 'State', 'Step'],
      rows: workflows
        .slice(0, 12)
        .map(workflow => [text(workflow.name || workflow.id), text(workflow.engine), text(workflow.state), text(workflow.current_step)])
    },
    {
      kind: 'table',
      title: 'Pending approvals',
      hint: `Source: ${sourceLabel(approvals.source)}`,
      columns: ['Item', 'Status', 'Detail'],
      rows: list(approvals.items)
        .map(record)
        .slice(0, 12)
        .map(item => [text(item.title || item.name || item.id), text(item.status), text(item.detail || item.reason || item.action)])
    },
    {
      kind: 'table',
      title: 'Cron jobs',
      hint: 'Existing Hermes scheduler — manage from the Cron page',
      columns: JOB_COLUMNS,
      rows: jobRows(payload.cron)
    },
    {
      kind: 'table',
      title: 'Automation jobs',
      columns: JOB_COLUMNS,
      rows: jobRows(payload.automation)
    }
  ]
}

function describeSystem(payload: GuardianPayload): GuardianBlock[] {
  const storage = record(payload.storage)
  const capacity = record(storage.capacity)

  return [
    {
      kind: 'stats',
      items: [
        { label: 'Free (GB)', value: text(capacity.free_gb) },
        { label: 'Total (GB)', value: text(capacity.total_gb) },
        { label: 'Used', value: `${text(capacity.used_percent)}%` },
        { label: 'Hermes size (GB)', value: text(capacity.hermes_size_gb) }
      ]
    },
    {
      kind: 'table',
      title: 'Department links',
      hint: 'Jump to the Hermes pages that own each area — nothing is duplicated here',
      columns: ['Area', 'Description'],
      rows: list(payload.links)
        .map(record)
        .map(link => [text(link.label), text(link.description)])
    },
    {
      kind: 'table',
      title: 'Storage locations',
      hint: 'Capacity and location overview (the integrity sweep stays an explicit System-page action)',
      columns: ['Location', 'Path', 'Readable', 'Writable'],
      rows: list(storage.locations)
        .map(record)
        .slice(0, 12)
        .map(location => [
          text(location.name),
          text(location.path),
          location.readable === true ? 'yes' : 'no',
          location.writable === true ? 'yes' : 'no'
        ])
    },
    {
      kind: 'table',
      title: 'Cron jobs',
      columns: JOB_COLUMNS,
      rows: jobRows(payload.cron)
    }
  ]
}
