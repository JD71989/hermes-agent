/**
 * Guardian — Guardian V5 capabilities as nine Hermes departments.
 *
 * Registers the Command Centre hub plus one route per department, a sidebar
 * entry and a palette command. Every surface is read-only and reads the
 * existing `/api/guardian/*` projections; there is no second database,
 * orchestrator or chat surface here.
 */

import {
  host,
  type HermesPlugin,
  PALETTE_AREA,
  type PaletteContribution,
  type RouteContribution,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  type SidebarNavContribution
} from '@hermes/plugin-sdk'

import { GuardianDepartmentPage } from './department-page'
import { GUARDIAN_DEPARTMENTS } from './departments'
import { GuardianHubPage } from './hub'

const plugin: HermesPlugin = {
  id: 'guardian',
  name: 'Guardian',
  description:
    'Guardian V5 capabilities as nine Hermes departments — Business & Revenue, Marketing, Media & Creators, Crypto, Trading, Intelligence, CyberLab, Automation and System Administration. Read-only surfaces over existing stores; paper and research only.',
  defaultEnabled: true,
  register(ctx) {
    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/guardian' } satisfies RouteContribution,
        render: () => <GuardianHubPage />
      },
      ...GUARDIAN_DEPARTMENTS.map(department => ({
        id: `page-${department.id}`,
        area: ROUTES_AREA,
        data: { path: department.path } satisfies RouteContribution,
        render: () => <GuardianDepartmentPage id={department.id} />
      })),
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        order: 40,
        data: { codicon: 'shield', label: 'Guardian', path: '/guardian' } satisfies SidebarNavContribution
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: 'guardian.open',
          label: 'Guardian: Open command centre',
          keywords: ['guardian', 'revenue', 'departments', 'trading', 'automation'],
          run: () => host.navigate('/guardian')
        } satisfies PaletteContribution
      }
    ])
  }
}

export default plugin
