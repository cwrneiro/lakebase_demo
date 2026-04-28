import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { toast } from 'sonner'
import type { UserDetail as UserDetailT } from '@/lib/types'
import { api } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { ScoreBadge } from '@/components/ScoreBadge'
import { ExplainPanel } from '@/components/ExplainPanel'
import { RecommendationsPanel } from '@/components/RecommendationsPanel'
import { ActionHistory } from '@/components/ActionHistory'
import { formatRelativeTime } from '@/lib/utils'

export function UserDetail() {
  const { userId = '' } = useParams()
  const [data, setData] = useState<UserDetailT | null>(null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(() => {
    const ctrl = new AbortController()
    setLoading(true)
    api
      .getUser(userId, ctrl.signal)
      .then(setData)
      .catch((e) => {
        if (ctrl.signal.aborted) return
        toast.error('Failed to load user', { description: String(e) })
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false)
      })
    return () => ctrl.abort()
  }, [userId])

  useEffect(() => reload(), [reload])

  return (
    <div className="space-y-4">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to queue
      </Link>

      {loading && !data && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-40 lg:col-span-2" />
          <Skeleton className="h-40" />
        </div>
      )}

      {data && (
        <>
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <CardTitle className="font-mono text-base">{data.user_id}</CardTitle>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-[var(--color-muted)]">
                    {data.plan_tier && <Badge variant="outline">{data.plan_tier}</Badge>}
                    {data.segment && <Badge variant="muted">{data.segment}</Badge>}
                    {data.region && <span>{data.region}</span>}
                    {data.signup_date && (
                      <span>· joined {new Date(data.signup_date).toLocaleDateString()}</span>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  <ScoreBadge score={data.churn_risk_score} size="lg" />
                  <p className="mt-1 text-xs text-[var(--color-muted)]">
                    {data.engagement_tier ?? 'unknown'} risk · scored{' '}
                    {formatRelativeTime(data.last_scored_at)}
                  </p>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3 lg:grid-cols-6">
                <Stat label="Sessions (30d)" value={data.sessions_30d} />
                <Stat label="Tickets (30d)" value={data.support_tickets_30d} />
                <Stat label="Pay fails (90d)" value={data.payment_failures_90d} />
                <Stat label="Days since event" value={data.days_since_last_event} />
                <Stat label="Tenure (days)" value={data.tenure_days} />
                <Stat
                  label="MRR"
                  value={data.mrr_current ? `$${data.mrr_current}` : '—'}
                />
              </dl>
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-2">
              <RecommendationsPanel
                userId={data.user_id}
                recommendations={data.recommendations}
                onActionTaken={reload}
              />
              <ActionHistory actions={data.recent_actions} />
            </div>
            <div className="space-y-4">
              <ExplainPanel userId={data.user_id} />
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-[var(--color-muted)]">{label}</dt>
      <dd className="mt-1 text-base font-semibold tabular-nums">{value ?? '—'}</dd>
    </div>
  )
}
