import type {
  ActionCreate,
  Action,
  ExplainResponse,
  RescoreResponse,
  SortKey,
  UserDetail,
  UserListResponse,
} from './types'

class ApiError extends Error {
  status: number
  body: string
  constructor(status: number, body: string) {
    super(`${status}: ${body}`)
    this.status = status
    this.body = body
  }
}

async function req<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    signal,
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, body)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  listUsers(
    params: { limit?: number; offset?: number; sort?: SortKey; tier?: string } = {},
    signal?: AbortSignal,
  ): Promise<UserListResponse> {
    const q = new URLSearchParams()
    if (params.limit !== undefined) q.set('limit', String(params.limit))
    if (params.offset !== undefined) q.set('offset', String(params.offset))
    if (params.sort) q.set('sort', params.sort)
    if (params.tier) q.set('tier', params.tier)
    const qs = q.toString() ? `?${q.toString()}` : ''
    return req<UserListResponse>(`/users${qs}`, {}, signal)
  },

  getUser(userId: string, signal?: AbortSignal): Promise<UserDetail> {
    return req<UserDetail>(`/users/${encodeURIComponent(userId)}`, {}, signal)
  },

  createAction(userId: string, body: ActionCreate): Promise<Action> {
    return req<Action>(`/users/${encodeURIComponent(userId)}/actions`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  explainScore(userId: string, signal?: AbortSignal): Promise<ExplainResponse> {
    return req<ExplainResponse>(
      `/users/${encodeURIComponent(userId)}/explain`,
      { method: 'POST', body: '{}' },
      signal,
    )
  },

  rescore(): Promise<RescoreResponse> {
    return req<RescoreResponse>('/admin/rescore', { method: 'POST', body: '{}' })
  },
}

export { ApiError }
