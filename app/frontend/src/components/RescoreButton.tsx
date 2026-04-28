import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'

export function RescoreButton({ onTriggered }: { onTriggered?: () => void }) {
  const [pending, setPending] = useState(false)

  async function rescore() {
    setPending(true)
    try {
      const r = await api.rescore()
      toast.success('Re-score job triggered', {
        description: r.run_page_url ? 'Open job run in Databricks' : `Run ${r.run_id}`,
        action: r.run_page_url
          ? {
              label: 'Open',
              onClick: () => window.open(r.run_page_url!, '_blank', 'noopener'),
            }
          : undefined,
      })
      onTriggered?.()
    } catch (e) {
      toast.error('Re-score failed', { description: String(e) })
    } finally {
      setPending(false)
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={rescore} disabled={pending}>
      <RefreshCw className={pending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
      Re-score
    </Button>
  )
}
