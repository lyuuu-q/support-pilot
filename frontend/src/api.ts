import type { AgentResponse, ApiErrorBody, CurrentUser, RunEvent, Ticket, TicketStatus, TraceEvent } from './types'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'
// 必须与后端 SUPPORT_PILOT_AUTH_CSRF_COOKIE / SUPPORT_PILOT_AUTH_CSRF_HEADER 保持一致。
const CSRF_COOKIE = 'support_pilot_csrf'
const CSRF_HEADER = 'X-CSRF-Token'
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

function readCookie(name: string): string {
  const prefix = `${name}=`
  for (const part of document.cookie.split(';')) {
    const trimmed = part.trim()
    if (trimmed.startsWith(prefix)) return decodeURIComponent(trimmed.slice(prefix.length))
  }
  return ''
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
  ) {
    super(message)
  }
}

async function parseError(response: Response): Promise<ApiError> {
  const body = (await response.json().catch(() => ({}))) as ApiErrorBody
  return new ApiError(
    body.error?.message ?? `请求失败 (${response.status})`,
    body.error?.code ?? 'request_failed',
    response.status,
  )
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  }
  if (UNSAFE_METHODS.has(method)) headers[CSRF_HEADER] = readCookie(CSRF_COOKIE)
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers,
  })
  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function login(email: string, password: string): Promise<CurrentUser> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!response.ok) throw await parseError(response)
  const body = (await response.json()) as { user: CurrentUser }
  return body.user
}

export const getCurrentUser = () => request<CurrentUser>('/auth/me')

export const refreshSession = () =>
  request<{ user: CurrentUser }>('/auth/refresh', { method: 'POST' }).then((body) => body.user)

export const logout = () => request<void>('/auth/logout', { method: 'POST' })

/** Restore a browser session: reuse the access cookie, rotate once, otherwise stay logged out. */
export async function restoreSession(): Promise<CurrentUser | null> {
  try {
    return await getCurrentUser()
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error
  }
  try {
    return await refreshSession()
  } catch {
    return null
  }
}

interface StreamCallbacks {
  onProgress: (event: TraceEvent) => void
  onResult: (result: AgentResponse) => void
  onEventId?: (eventId: string) => void
}

export async function streamAgent(
  payload: Record<string, unknown>,
  callbacks: StreamCallbacks,
  idempotencyKey?: string,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/agent/resolve/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      [CSRF_HEADER]: readCookie(CSRF_COOKIE),
      ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  })
  if (!response.ok) throw await parseError(response)
  if (!response.body) throw new ApiError('浏览器没有收到事件流', 'stream_unavailable', 0)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) dispatchSseBlock(block, callbacks)
    if (done) break
  }
  if (buffer.trim()) dispatchSseBlock(buffer, callbacks)
}

function dispatchSseBlock(block: string, callbacks: StreamCallbacks): void {
  let eventName = 'message'
  let eventId: string | undefined
  const dataLines: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('id:')) eventId = line.slice(3).trim()
    if (line.startsWith('event:')) eventName = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  if (!dataLines.length) return
  if (eventId) callbacks.onEventId?.(eventId)
  const payload = JSON.parse(dataLines.join('\n')) as unknown
  if (eventName === 'progress') callbacks.onProgress(payload as TraceEvent)
  if (eventName === 'result') callbacks.onResult(payload as AgentResponse)
  if (eventName === 'error') {
    const body = payload as ApiErrorBody
    throw new ApiError(body.error?.message ?? 'Agent 执行失败', body.error?.code ?? 'agent_failed', 200)
  }
}

export const listRunEvents = (runId: string, after = 0) =>
  request<{ items: RunEvent[] }>(`/agent/runs/${runId}/events?after=${after}&limit=500`)

export const resumeAgentRun = (runId: string) =>
  request<AgentResponse>(`/agent/runs/${runId}/resume`, { method: 'POST' })
export interface TicketListOptions {
  status?: TicketStatus
  q?: string
  cursor?: string
  limit?: number
}

export const listTickets = (options: TicketListOptions = {}) => {
  const params = new URLSearchParams()
  params.set('limit', String(options.limit ?? 20))
  if (options.status) params.set('status', options.status)
  if (options.q?.trim()) params.set('q', options.q.trim())
  if (options.cursor) params.set('cursor', options.cursor)
  return request<{ items: Ticket[]; total: number; next_cursor: string | null }>(
    `/tickets?${params.toString()}`,
  )
}

export const claimTicket = (ticket: Ticket) =>
  request<Ticket>(`/tickets/${ticket.id}/claim`, {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ expected_version: ticket.version }),
  })

export const transitionTicket = (ticket: Ticket, toStatus: string, reason: string) =>
  request<Ticket>(`/tickets/${ticket.id}/transitions`, {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ to_status: toStatus, expected_version: ticket.version, reason }),
  })

export const submitFeedback = (ticket: Ticket, payload: Record<string, unknown>) =>
  request(`/tickets/${ticket.id}/feedback`, {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify(payload),
  })
