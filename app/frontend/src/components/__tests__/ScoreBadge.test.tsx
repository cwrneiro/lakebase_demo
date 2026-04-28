import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ScoreBadge } from '@/components/ScoreBadge'

// Thresholds in `tierFor` (ScoreBadge.tsx):
//   >= 70  -> high   (--color-risk-high)
//   >= 40  -> medium (--color-risk-med)
//   <  40  -> low    (--color-risk-low)
// We assert the inline `background-color` style picks the right CSS var since
// titles/labels aren't user-visible to a screen reader; the color is the
// load-bearing signal.

describe('ScoreBadge', () => {
  it('renders the score number when provided', () => {
    render(<ScoreBadge score={42} />)
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('uses the high-risk color when score >= 70', () => {
    render(<ScoreBadge score={85} />)
    const el = screen.getByText('85')
    expect(el).toHaveStyle({ backgroundColor: 'var(--color-risk-high)' })
    expect(el).toHaveAttribute('title', 'Churn risk: 85')
  })

  it('uses the medium color when 40 <= score < 70', () => {
    render(<ScoreBadge score={55} />)
    expect(screen.getByText('55')).toHaveStyle({
      backgroundColor: 'var(--color-risk-med)',
    })
  })

  it('uses the low color when score < 40', () => {
    render(<ScoreBadge score={12} />)
    expect(screen.getByText('12')).toHaveStyle({
      backgroundColor: 'var(--color-risk-low)',
    })
  })

  it('renders an em-dash placeholder when score is null', () => {
    render(<ScoreBadge score={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
