import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDown, ArrowUp, Filter } from 'lucide-react'
import { toast } from 'sonner'
import type { SortKey, UserListResponse } from '@/lib/types'
import { api } from '@/lib/api'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { ScoreBadge } from '@/components/ScoreBadge'
import { formatRelativeTime, cn } from '@/lib/utils'

const PAGE_SIZE = 50

export function UserList() {
  const [data, setData] = useState<UserListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const [sort, setSort] = useState<SortKey>('risk_desc')
  const [tierFilter, setTierFilter] = useState<string>('')

  useEffect(() => {
    const ctrl = new AbortController()
    setLoading(true)
    api
      .listUsers(
        { limit: PAGE_SIZE, offset: page * PAGE_SIZE, sort, tier: tierFilter || undefined },
        ctrl.signal,
      )
      .then(setData)
      .catch((e) => {
        if (ctrl.signal.aborted) return
        toast.error('Failed to load users', { description: String(e) })
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false)
      })
    return () => ctrl.abort()
  }, [page, sort, tierFilter])

  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Risk-ranked operator queue</h1>
          <p className="text-sm text-[var(--color-muted)]">
            Users synced live from <code>scored.user_scores</code> via Lakebase synced
            tables. Click a row to triage.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-[var(--color-muted)]" />
          <select
            value={tierFilter}
            onChange={(e) => {
              setTierFilter(e.target.value)
              setPage(0)
            }}
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-card)] px-2 py-1 text-sm"
          >
            <option value="">All tiers</option>
            <option value="high">High risk</option>
            <option value="medium">Medium risk</option>
            <option value="low">Low risk</option>
          </select>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                <th className="px-4 py-3 font-medium">User</th>
                <th className="px-4 py-3 font-medium">Plan</th>
                <th className="px-4 py-3 font-medium">Region</th>
                <SortableHeader
                  label="Risk"
                  active={sort.startsWith('risk_')}
                  direction={sort === 'risk_desc' ? 'desc' : 'asc'}
                  onClick={() =>
                    setSort(sort === 'risk_desc' ? 'risk_asc' : 'risk_desc')
                  }
                />
                <th className="px-4 py-3 font-medium">Top recommendation</th>
                <th className="px-4 py-3 font-medium">Last action</th>
              </tr>
            </thead>
            <tbody>
              {loading &&
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={`s-${i}`} className="border-b border-[var(--color-border)]">
                    {Array.from({ length: 6 }).map((__, j) => (
                      <td key={j} className="px-4 py-3">
                        <Skeleton className="h-4 w-24" />
                      </td>
                    ))}
                  </tr>
                ))}
              {!loading &&
                data?.items.map((u) => (
                  <tr
                    key={u.user_id}
                    className="border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-bg)]"
                  >
                    <td className="px-4 py-3">
                      <Link
                        to={`/users/${encodeURIComponent(u.user_id)}`}
                        className="font-mono text-xs text-[var(--color-accent)] hover:underline"
                      >
                        {u.user_id.slice(0, 8)}…
                      </Link>
                      {u.segment && (
                        <span className="ml-2 text-xs text-[var(--color-muted)]">
                          {u.segment}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {u.plan_tier && <Badge variant="outline">{u.plan_tier}</Badge>}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--color-muted)]">
                      {u.region ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      <ScoreBadge score={u.churn_risk_score} />
                    </td>
                    <td className="px-4 py-3 text-[var(--color-muted)]">
                      {u.top_recommendation ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--color-muted)]">
                      {formatRelativeTime(u.last_action_at)}
                    </td>
                  </tr>
                ))}
              {!loading && data && data.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-[var(--color-muted)]">
                    No users match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between text-sm text-[var(--color-muted)]">
        <span>
          Page {page + 1} of {totalPages} · {total} total
        </span>
        <div className="flex gap-2">
          <button
            disabled={page === 0}
            onClick={() => setPage(page - 1)}
            className="rounded-md border border-[var(--color-border)] px-3 py-1 disabled:opacity-50"
          >
            Previous
          </button>
          <button
            disabled={page + 1 >= totalPages}
            onClick={() => setPage(page + 1)}
            className="rounded-md border border-[var(--color-border)] px-3 py-1 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}

function SortableHeader({
  label,
  active,
  direction,
  onClick,
}: {
  label: string
  active: boolean
  direction: 'asc' | 'desc'
  onClick: () => void
}) {
  return (
    <th className="px-4 py-3 font-medium">
      <button
        onClick={onClick}
        className={cn(
          'inline-flex items-center gap-1',
          active && 'text-[var(--color-fg)]',
        )}
      >
        {label}
        {active &&
          (direction === 'desc' ? (
            <ArrowDown className="h-3 w-3" />
          ) : (
            <ArrowUp className="h-3 w-3" />
          ))}
      </button>
    </th>
  )
}
