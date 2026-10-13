import { afterEach, describe, expect, it, vi } from 'vitest'
import { listRunEvents, listTickets, login, resumeAgentRun, streamAgent } from './api'

afterEach(() => {
  document.cookie = 'support_pilot_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
})

function streamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
      controller.close()
    },
  })
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

describe('listTickets', () => {
  it('builds status, search, cursor and limit query parameters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0, next_cursor: null }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listTickets({ status: 'open', q: 'TKT-1', cursor: 'abc', limit: 5 })

    const url = String(fetchMock.mock.calls[0]?.[0])
    expect(url).toContain('/tickets?')
    expect(url).toContain('limit=5')
    expect(url).toContain('status=open')
    expect(url).toContain('q=TKT-1')
    expect(url).toContain('cursor=abc')
  })
})
describe('browser session requests', () => {
  it('sends cookies and the CSRF header on writes', async () => {
    document.cookie = 'support_pilot_csrf=csrf-from-cookie; path=/'
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ items: [], total: 0, next_cursor: null }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listTickets({ limit: 5 })
    await resumeAgentRun('run-1')

    expect(fetchMock.mock.calls[0]?.[1]).toEqual(expect.objectContaining({ credentials: 'include' }))
    const readHeaders = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect((readHeaders.headers as Record<string, string>)['X-CSRF-Token']).toBeUndefined()
    const writeHeaders = fetchMock.mock.calls[1]?.[1] as RequestInit
    expect((writeHeaders.headers as Record<string, string>)['X-CSRF-Token']).toBe('csrf-from-cookie')
  })

  it('returns the signed-in identity without exposing a token', async () => {
    const body = { user: { id: 'u1', role: 'tenant_admin' }, csrf_token: 'csrf-1', expires_in: 1800 }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    ))

    const user = await login('alpha.admin@example.com', 'SupportPilotDemo!2026')

    expect(user).toEqual(body.user)
    expect(JSON.stringify(user)).not.toContain('access_token')
  })
})

describe('streamAgent', () => {
  it('parses SSE events even when chunks split an event boundary', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      'event: progress\ndata: {"sequence":1,"node":"class',
      'ify","status":"succeeded","detail":"done"}\n\nevent: result\ndata: {"outcome":"answered"}\n\n',
    ])))
    const progress = vi.fn()
    const result = vi.fn()

    await streamAgent({ message: 'hello' }, { onProgress: progress, onResult: result })

    expect(progress).toHaveBeenCalledWith(expect.objectContaining({ node: 'classify' }))
    expect(result).toHaveBeenCalledWith(expect.objectContaining({ outcome: 'answered' }))
  })

  it('forwards AbortSignal to fetch', async () => {
    const controller = new AbortController()
    const fetchMock = vi.fn().mockResolvedValue(
      streamResponse(['event: result\ndata: {"outcome":"answered"}\n\n']),
    )
    vi.stubGlobal('fetch', fetchMock)

    await streamAgent(
      { message: 'hello' },
      { onProgress: vi.fn(), onResult: vi.fn() },
      undefined,
      controller.signal,
    )

    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ signal: controller.signal }),
    )
  })
  it('reports SSE event ids', async () => {
    const ids: string[] = []
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      'id: run-1:1\nevent: progress\ndata: {"sequence":1,"node":"classify","status":"succeeded","detail":"done"}\n\n',
    ])))

    await streamAgent({ message: 'hello' }, {
      onProgress: vi.fn(),
      onResult: vi.fn(),
      onEventId: (eventId) => ids.push(eventId),
    })

    expect(ids).toEqual(['run-1:1'])
  })

  it('builds run replay and resume requests', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ request_id: 'run-1' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    vi.stubGlobal('fetch', fetchMock)

    await listRunEvents('run-1', 2)
    await resumeAgentRun('run-1')

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/agent/runs/run-1/events?after=2')
    expect(fetchMock.mock.calls[1]?.[1]).toEqual(expect.objectContaining({ method: 'POST' }))
  })
  it('raises controlled SSE errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      'event: error\ndata: {"error":{"code":"request_precondition_failed","message":"missing draft"}}\n\n',
    ])))

    await expect(streamAgent({}, { onProgress: vi.fn(), onResult: vi.fn() }))
      .rejects.toMatchObject({ code: 'request_precondition_failed', message: 'missing draft' })
  })
})
