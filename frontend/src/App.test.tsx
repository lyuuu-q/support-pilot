import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const customer = {
  id: '10000000-0000-0000-0000-000000000001',
  tenant_id: '20000000-0000-0000-0000-000000000001',
  email: 'alpha.admin@example.com',
  display_name: 'Alpha Admin',
  role: 'tenant_admin',
}

const supportAgent = {
  ...customer,
  id: '30000000-0000-0000-0000-000000000001',
  tenant_id: null,
  email: 'support.agent@example.com',
  display_name: 'Support Agent',
  role: 'support_agent',
}

const ticket = {
  id: '40000000-0000-0000-0000-000000000001', public_code: 'SP-1001', tenant_id: customer.tenant_id,
  status: 'open', severity: 'high', category: 'incident', summary: 'Webhook delivery failed',
  description: 'Callbacks have failed since 10:00.', diagnostic_context: { component_code: 'webhook' },
  escalation_reason: 'user_requested', assignee_id: null, agent_run_id: null, version: 1,
  created_at: '2026-08-31T10:00:00Z', updated_at: '2026-08-31T10:00:00Z', transitions: [], replayed: false,
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

function sseResponse(): Response {
  const body = [
    'event: progress\ndata: {"sequence":1,"node":"preflight_safety","status":"succeeded","detail":"safe"}\n\n',
    'event: result\ndata: {"request_id":"r","session_id":"s","trace_id":"trace-123456789","outcome":"answered","intent":"knowledge","risk_level":"R1","message":"请按 Retry-After 等待后重试。","response_mode":"extractive","citations":[],"claims":[{"claim_id":"c1-1","text":"客户端应以 Retry-After 为准","chunk_id":"chunk-1","source_uri":"kb://exampleapi/reference/rate-limits","citation_index":0,"verification":{"supported":true,"method":"verbatim","support_score":1.0,"missing_terms":[]}}],"tool_result":null,"ticket_draft":null,"required_fields":[],"escalation_reason":null,"conversation_status":"completed","model_usage":{"model_calls":0,"total_tokens":0,"estimated_cost_cny":0},"trace":[]}\n\n',
  ].join('')
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SupportPilot console', () => {
  it('restores the cookie session and renders live Agent progress', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/auth/me')) return jsonResponse(customer)
      if (url.endsWith('/agent/resolve/stream')) return sseResponse()
      throw new Error(`unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    await screen.findByText('Alpha Admin')
    expect(fetchMock.mock.calls[0]?.[1]).toEqual(expect.objectContaining({ credentials: 'include' }))

    await screen.findByText('Alpha Admin')
    await userEvent.click(screen.getByRole('button', { name: '开始诊断' }))

    expect(await screen.findByText('请按 Retry-After 等待后重试。')).toBeInTheDocument()
    expect(screen.getByText('preflight_safety')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '逐条主张' })).toBeInTheDocument()
    expect(screen.getByText('客户端应以 Retry-After 为准')).toBeInTheDocument()
    expect(screen.getByText('支持')).toBeInTheDocument()
  })

  it('stops waiting and safely retries the last action', async () => {
    let streamCalls = 0
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/auth/me')) return jsonResponse(customer)
      if (url.endsWith('/agent/resolve/stream')) {
        streamCalls += 1
        if (streamCalls === 1) {
          return new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () => {
              reject(new DOMException('aborted', 'AbortError'))
            })
          })
        }
        return sseResponse()
      }
      throw new Error(`unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    await screen.findByText('Alpha Admin')
    await userEvent.click(screen.getByRole('button', { name: '开始诊断' }))
    await userEvent.click(await screen.findByRole('button', { name: '停止等待' }))

    expect(await screen.findByRole('button', { name: '重试上一步' })).toBeInTheDocument()
    expect(screen.getByText(/已停止等待/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '重试上一步' }))
    expect(await screen.findByText('请按 Retry-After 等待后重试。')).toBeInTheDocument()
    expect(streamCalls).toBe(2)
  })
  it('lets a support agent claim an open handoff ticket', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/me')) return jsonResponse(supportAgent)
      if (url.includes('/tickets?')) return jsonResponse({ items: [ticket], total: 1 })
      if (url.endsWith(`/tickets/${ticket.id}/claim`)) {
        return jsonResponse({ ...ticket, status: 'triaged', assignee_id: supportAgent.id, version: 2, transitions: [{ id: 't1', from_status: 'open', to_status: 'triaged', actor_id: supportAgent.id, reason: 'ticket_claimed', created_at: '2026-08-31T10:01:00Z' }] })
      }
      throw new Error(`unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    await screen.findByRole('heading', { name: 'Webhook delivery failed' })
    await userEvent.click(screen.getByRole('button', { name: '认领并分诊' }))

    await waitFor(() => expect(screen.getAllByText('triaged')).not.toHaveLength(0))
    expect(screen.getByText('open → triaged')).toBeInTheDocument()
  })
  it('recovers a dropped stream from persisted events', async () => {
    const recoveredResult = {
      request_id: 'run-1', session_id: 's', trace_id: 'trace-recovered', outcome: 'answered',
      intent: 'knowledge', risk_level: 'R1', message: '已恢复的回答', response_mode: 'extractive',
      citations: [], claims: [], tool_result: null, ticket_draft: null, required_fields: [],
      escalation_reason: null, conversation_status: 'completed',
      model_usage: { model_calls: 0, total_tokens: 0, estimated_cost_cny: 0 }, trace: [],
    }
    const encoder = new TextEncoder()
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/me')) return jsonResponse(customer)
      if (url.endsWith('/agent/resolve/stream')) {
        let step = 0
        return new Response(new ReadableStream({
          pull(controller) {
            if (step === 0) {
              step = 1
              controller.enqueue(encoder.encode('id: run-1:1\nevent: progress\ndata: {"sequence":1,"node":"preflight_safety","status":"succeeded","detail":"safe"}\n\n'))
              return
            }
            controller.error(new Error('network down'))
          },
        }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
      }
      if (url.includes('/agent/runs/run-1/events')) {
        return jsonResponse({ items: [
          { sequence: 1, event: 'progress', event_id: 'run-1:1', payload: { sequence: 1, node: 'preflight_safety', status: 'succeeded', detail: 'safe' } },
          { sequence: 2, event: 'result', event_id: 'run-1:2', payload: recoveredResult },
        ] })
      }
      throw new Error(`unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    await screen.findByText('Alpha Admin')
    await userEvent.click(screen.getByRole('button', { name: '开始诊断' }))

    expect(await screen.findByText('已恢复的回答')).toBeInTheDocument()
    expect(screen.getByText('已从服务端恢复断线前的事件。')).toBeInTheDocument()
    expect(screen.getByText('preflight_safety')).toBeInTheDocument()
  })

  it('falls back to the login form when no session can be restored', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/auth/me')) {
        return new Response(JSON.stringify({ error: { code: 'authentication_required', message: 'no session' } }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.endsWith('/auth/refresh')) {
        return new Response(JSON.stringify({ error: { code: 'authentication_required', message: 'no session' } }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.endsWith('/auth/login')) {
        expect(init?.credentials).toBe('include')
        return jsonResponse({ user: customer, csrf_token: 'csrf-1', expires_in: 1800 })
      }
      throw new Error(`unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    await userEvent.type(await screen.findByLabelText('密码'), 'SupportPilotDemo!2026')
    await userEvent.click(screen.getByRole('button', { name: '进入工作台' }))

    expect(await screen.findByText('Alpha Admin')).toBeInTheDocument()
  })
})
