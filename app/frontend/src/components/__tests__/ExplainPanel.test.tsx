import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// `vi.mock` is hoisted above imports; closure variables it references must
// be hoisted too via `vi.hoisted`.
const { explainScoreMock, toastMock, FakeApiError } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    body: string
    constructor(status: number, body: string) {
      super(`${status}: ${body}`)
      this.status = status
      this.body = body
    }
  }
  return {
    explainScoreMock: vi.fn(),
    toastMock: { info: vi.fn(), error: vi.fn(), success: vi.fn() },
    FakeApiError,
  }
})

vi.mock('@/lib/api', () => ({
  api: { explainScore: explainScoreMock },
  ApiError: FakeApiError,
}))

vi.mock('sonner', () => ({ toast: toastMock }))

import { ExplainPanel } from '@/components/ExplainPanel'

beforeEach(() => {
  explainScoreMock.mockReset()
  toastMock.info.mockReset()
  toastMock.error.mockReset()
})

describe('ExplainPanel', () => {
  it('shows skeletons while the explain request is in flight', async () => {
    let resolveFn: (v: { user_id: string; rationale: string; model: string }) => void = () => {}
    explainScoreMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFn = resolve
      }),
    )

    const { container } = render(<ExplainPanel userId="u_001" />)
    await userEvent.click(screen.getByRole('button', { name: /Generate/i }))

    // Button copy flips to "Thinking…" and the skeleton placeholders render.
    expect(screen.getByRole('button', { name: /Thinking/i })).toBeInTheDocument()
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)

    // Resolve to drain the promise so the test cleans up.
    resolveFn({ user_id: 'u_001', rationale: 'done', model: 'm' })
    await waitFor(() => expect(screen.queryByRole('button', { name: /Thinking/i })).toBeNull())
  })

  it('calls toast.info when the API returns 503 (LLM disabled)', async () => {
    explainScoreMock.mockRejectedValueOnce(new FakeApiError(503, 'disabled'))

    render(<ExplainPanel userId="u_001" />)
    await userEvent.click(screen.getByRole('button', { name: /Generate/i }))

    await waitFor(() => expect(toastMock.info).toHaveBeenCalled())
    expect(toastMock.info.mock.calls[0][0]).toMatch(/LLM explain disabled/i)
    // After 503 we display the in-card disabled message instead of the button.
    expect(screen.getByText(/Foundation Model panel disabled/i)).toBeInTheDocument()
  })

  it('renders the rationale text on a successful response', async () => {
    explainScoreMock.mockResolvedValueOnce({
      user_id: 'u_001',
      rationale: 'High risk: payment failures and engagement decline.',
      model: 'databricks-claude-sonnet-4-5',
    })

    render(<ExplainPanel userId="u_001" />)
    await userEvent.click(screen.getByRole('button', { name: /Generate/i }))

    expect(
      await screen.findByText(/High risk: payment failures and engagement decline\./i),
    ).toBeInTheDocument()
    expect(screen.getByText('databricks-claude-sonnet-4-5')).toBeInTheDocument()
  })
})
