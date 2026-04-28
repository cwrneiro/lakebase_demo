import { useState } from 'react'
import { Check, X, Clock } from 'lucide-react'
import { toast } from 'sonner'
import type { Recommendation, Decision } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { api } from '@/lib/api'

interface Props {
  userId: string
  recommendations: Recommendation[]
  onActionTaken: () => void
}

export function RecommendationsPanel({ userId, recommendations, onActionTaken }: Props) {
  const [pending, setPending] = useState<string | null>(null)

  async function act(rec: Recommendation, decision: Decision) {
    setPending(rec.recommendation_id)
    try {
      await api.createAction(userId, {
        recommendation_id: rec.recommendation_id,
        decision,
      })
      toast.success(`Marked "${rec.action_label}" as ${decision}`)
      onActionTaken()
    } catch (e) {
      toast.error('Action failed', { description: String(e) })
    } finally {
      setPending(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recommended actions</CardTitle>
      </CardHeader>
      <CardContent>
        {recommendations.length === 0 ? (
          <p className="text-sm text-[var(--color-muted)]">
            No active recommendations for this user.
          </p>
        ) : (
          <ul className="space-y-3">
            {recommendations.map((rec) => (
              <li
                key={rec.recommendation_id}
                className="flex flex-col gap-3 rounded-md border border-[var(--color-border)] p-4 sm:flex-row sm:items-start sm:justify-between"
              >
                <div className="flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">P{rec.priority}</Badge>
                    <span className="font-medium">{rec.action_label}</span>
                  </div>
                  {rec.rationale && (
                    <p className="text-sm text-[var(--color-muted)]">{rec.rationale}</p>
                  )}
                  <p className="font-mono text-xs text-[var(--color-muted)]">
                    {rec.action_code}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button
                    size="sm"
                    variant="success"
                    disabled={pending !== null}
                    onClick={() => act(rec, 'accepted')}
                  >
                    <Check className="h-3.5 w-3.5" />
                    Accept
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={pending !== null}
                    onClick={() => act(rec, 'snoozed')}
                  >
                    <Clock className="h-3.5 w-3.5" />
                    Snooze
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={pending !== null}
                    onClick={() => act(rec, 'dismissed')}
                  >
                    <X className="h-3.5 w-3.5" />
                    Dismiss
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
