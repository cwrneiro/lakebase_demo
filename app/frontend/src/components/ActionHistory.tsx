import type { Action } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatRelativeTime } from '@/lib/utils'

const decisionVariant: Record<Action['decision'], 'default' | 'outline' | 'muted'> = {
  accepted: 'default',
  snoozed: 'outline',
  dismissed: 'muted',
}

export function ActionHistory({ actions }: { actions: Action[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Action history</CardTitle>
      </CardHeader>
      <CardContent>
        {actions.length === 0 ? (
          <p className="text-sm text-[var(--color-muted)]">
            No operator actions recorded for this user yet.
          </p>
        ) : (
          <ol className="space-y-3 border-l border-[var(--color-border)] pl-4">
            {actions.map((a) => (
              <li key={a.action_id} className="relative">
                <div className="absolute -left-[21px] top-1 h-2 w-2 rounded-full bg-[var(--color-accent)]" />
                <div className="flex items-center gap-2">
                  <Badge variant={decisionVariant[a.decision]}>{a.decision}</Badge>
                  <span className="text-xs text-[var(--color-muted)]">
                    {formatRelativeTime(a.created_at)} · {a.operator}
                  </span>
                </div>
                {a.notes && <p className="mt-1 text-sm">{a.notes}</p>}
                {a.recommendation_id && (
                  <p className="mt-0.5 font-mono text-[10px] text-[var(--color-muted)]">
                    rec {a.recommendation_id.slice(0, 8)}…
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}
