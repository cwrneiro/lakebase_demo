import { cn } from '@/lib/utils'

interface ScoreBadgeProps {
  score: number | null | undefined
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

function tierFor(score: number) {
  if (score >= 70) return { label: 'high', bg: 'var(--color-risk-high)' }
  if (score >= 40) return { label: 'medium', bg: 'var(--color-risk-med)' }
  return { label: 'low', bg: 'var(--color-risk-low)' }
}

export function ScoreBadge({ score, size = 'md', className }: ScoreBadgeProps) {
  if (score == null) {
    return (
      <span
        className={cn(
          'inline-flex items-center rounded-full bg-[var(--color-border)] px-2 py-0.5 text-xs text-[var(--color-muted)]',
          className,
        )}
      >
        —
      </span>
    )
  }
  const { bg } = tierFor(score)
  const sizeClasses = {
    sm: 'px-1.5 py-0 text-[10px]',
    md: 'px-2.5 py-0.5 text-xs',
    lg: 'px-3 py-1 text-sm',
  }[size]
  return (
    <span
      title={`Churn risk: ${score}`}
      className={cn(
        'inline-flex items-center rounded-full font-semibold text-white tabular-nums',
        sizeClasses,
        className,
      )}
      style={{ backgroundColor: bg }}
    >
      {score}
    </span>
  )
}
