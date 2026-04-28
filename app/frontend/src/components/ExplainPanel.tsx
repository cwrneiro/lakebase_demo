import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api, ApiError } from '@/lib/api'

export function ExplainPanel({ userId }: { userId: string }) {
  const [loading, setLoading] = useState(false)
  const [explanation, setExplanation] = useState<string | null>(null)
  const [model, setModel] = useState<string | null>(null)
  const [unavailable, setUnavailable] = useState(false)

  async function explain() {
    setLoading(true)
    try {
      const r = await api.explainScore(userId)
      setExplanation(r.rationale)
      setModel(r.model)
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        setUnavailable(true)
        toast.info('LLM explain disabled in this deployment')
      } else {
        toast.error('Explain failed', { description: String(e) })
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4 text-[var(--color-accent)]" />
          Explain this score
        </CardTitle>
        {!explanation && !unavailable && (
          <Button size="sm" variant="outline" onClick={explain} disabled={loading}>
            {loading ? 'Thinking…' : 'Generate'}
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {unavailable && (
          <p className="text-sm text-[var(--color-muted)]">
            Foundation Model panel disabled. Set <code>ENABLE_LLM_EXPLAIN=true</code> in the
            app's environment to enable.
          </p>
        )}
        {!unavailable && !explanation && !loading && (
          <p className="text-sm text-[var(--color-muted)]">
            Generate a 2–3 sentence rationale from the score breakdown.
          </p>
        )}
        {loading && (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-9/12" />
          </div>
        )}
        {explanation && (
          <div className="space-y-2">
            <p className="text-sm leading-relaxed">{explanation}</p>
            {model && (
              <p className="text-xs text-[var(--color-muted)]">
                via <code>{model}</code>
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
