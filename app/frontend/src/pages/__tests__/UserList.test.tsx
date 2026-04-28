import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { UserListResponse } from '@/lib/types'

// `vi.mock` is hoisted above imports, so any closure variables it captures
// must be hoisted too — that's what `vi.hoisted` is for.
const { listUsersMock } = vi.hoisted(() => ({ listUsersMock: vi.fn() }))

vi.mock('@/lib/api', () => ({
  api: {
    listUsers: listUsersMock,
  },
  ApiError: class ApiError extends Error {
    status = 0
    body = ''
  },
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
  },
}))

import { UserList } from '@/pages/UserList'

function makeResponse(items: UserListResponse['items'], total = items.length): UserListResponse {
  return { items, total }
}

function renderUserList() {
  return render(
    <MemoryRouter>
      <UserList />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  listUsersMock.mockReset()
})

describe('UserList', () => {
  it('toggles sort between desc and asc when the Risk header is clicked', async () => {
    listUsersMock.mockResolvedValue(makeResponse([]))
    renderUserList()

    // Initial load uses the default sort.
    await waitFor(() => expect(listUsersMock).toHaveBeenCalled())
    expect(listUsersMock.mock.calls[0][0]).toMatchObject({ sort: 'risk_desc' })

    // Click the "Risk" sortable header — it should flip to risk_asc.
    const riskHeader = screen.getByRole('button', { name: /Risk/i })
    await userEvent.click(riskHeader)

    await waitFor(() =>
      expect(listUsersMock.mock.calls.at(-1)?.[0]).toMatchObject({ sort: 'risk_asc' }),
    )

    // Click again — back to risk_desc.
    await userEvent.click(riskHeader)
    await waitFor(() =>
      expect(listUsersMock.mock.calls.at(-1)?.[0]).toMatchObject({ sort: 'risk_desc' }),
    )
  })

  it('refetches with the new tier when the dropdown changes', async () => {
    listUsersMock.mockResolvedValue(makeResponse([]))
    renderUserList()

    await waitFor(() => expect(listUsersMock).toHaveBeenCalled())
    const initialCalls = listUsersMock.mock.calls.length

    const tierSelect = screen.getByRole('combobox')
    await userEvent.selectOptions(tierSelect, 'high')

    await waitFor(() => expect(listUsersMock.mock.calls.length).toBeGreaterThan(initialCalls))
    expect(listUsersMock.mock.calls.at(-1)?.[0]).toMatchObject({ tier: 'high', offset: 0 })
  })

  it('increments offset when Next is clicked', async () => {
    // Need >50 total so the Next button is enabled (PAGE_SIZE = 50).
    listUsersMock.mockResolvedValue(makeResponse([], 200))
    renderUserList()

    await waitFor(() => expect(listUsersMock).toHaveBeenCalled())
    expect(listUsersMock.mock.calls[0][0]).toMatchObject({ offset: 0 })

    const next = screen.getByRole('button', { name: /Next/i })
    await userEvent.click(next)

    await waitFor(() =>
      expect(listUsersMock.mock.calls.at(-1)?.[0]).toMatchObject({ offset: 50 }),
    )
  })

  it('shows the empty-state message when there are no users', async () => {
    listUsersMock.mockResolvedValue(makeResponse([]))
    renderUserList()

    expect(await screen.findByText('No users match these filters.')).toBeInTheDocument()
  })
})
