import { describe, expect, it, vi } from 'vitest'
import { listRunEvents, listTickets, resumeAgentRun, streamAgent } from './api'

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

    await listTickets('token', { status: 'open', q: 'TKT-1', cursor: 'abc', limit: 5 })

    const url = String(fetchMock.mock.calls[0]?.[0])
    expect(url).toContain('/tickets?')
    expect(url).toContain('limit=5')
    expect(url).toContain('status=open')
    expect(url).toContain('q=TKT-1')
    expect(url).toContain('cursor=abc')
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

    await streamAgent('token', { message: 'hello' }, { onProgress: progress, onResult: result })

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
      'token',
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

    await streamAgent('token', { message: 'hello' }, {
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

    await listRunEvents('token', 'run-1', 2)
    await resumeAgentRun('token', 'run-1')

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/agent/runs/run-1/events?after=2')
    expect(fetchMock.mock.calls[1]?.[1]).toEqual(expect.objectContaining({ method: 'POST' }))
  })
  it('raises controlled SSE errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      'event: error\ndata: {"error":{"code":"request_precondition_failed","message":"missing draft"}}\n\n',
    ])))

    await expect(streamAgent('token', {}, { onProgress: vi.fn(), onResult: vi.fn() }))
      .rejects.toMatchObject({ code: 'request_precondition_failed', message: 'missing draft' })
  })
})
