import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  claimTicket,
  getAuthProviders,
  listRunEvents,
  listTickets,
  login,
  logout,
  logoutAll,
  oidcStartUrl,
  resumeAgentRun,
  restoreSession,
  streamAgent,
  submitFeedback,
  transitionTicket,
} from './api'
import type { AuthProviders } from './api'
import type { AgentResponse, CurrentUser, Ticket, TicketStatus, TraceEvent } from './types'
import './styles.css'

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : '发生未知错误'
}

function Login({ onAuthenticated }: { onAuthenticated: (user: CurrentUser) => void }) {
  const [email, setEmail] = useState('alpha.admin@example.com')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [providers, setProviders] = useState<AuthProviders | null>(null)

  useEffect(() => {
    getAuthProviders().then(setProviders).catch(() => setProviders(null))
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const user = await login(email, password)
      onAuthenticated(user)
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-shell">
      <section className="login-copy">
        <div className="brand-mark">SP</div>
        <p className="eyebrow">SupportPilot · AI support operations</p>
        <h1>让每次技术支持都有证据、有边界、有接管路径。</h1>
        <p className="lede">检索企业知识与业务状态，经过置信度门控后自动回答或安全升级人工。</p>
        <div className="flow-strip"><span>识别</span><span>检索 / 工具</span><span>门控</span><span>人工闭环</span></div>
      </section>
      <form className="login-card" onSubmit={submit}>
        <p className="eyebrow">本地演示环境</p>
        <h2>登录控制台</h2>
        <label>邮箱<input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required /></label>
        <label>密码<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" required minLength={8} /></label>
        {error && <p className="error-banner" role="alert">{error}</p>}
        <button className="primary" disabled={busy}>{busy ? '验证中…' : '进入工作台'}</button>
        {providers?.oidc.enabled && <a className="primary oidc-login" href={oidcStartUrl()}>使用{providers.oidc.display_name}登录</a>}
        <small>JWT 仅保存在当前浏览器；退出后立即移除。</small>
      </form>
    </main>
  )
}

function TraceTimeline({ events }: { events: TraceEvent[] }) {
  return (
    <ol className="trace-list" aria-label="Agent 执行轨迹">
      {events.map((event) => <li key={`${event.sequence}-${event.node}`} className={event.status}>
        <span>{event.sequence}</span><div><strong>{event.node}</strong><p>{event.detail}</p></div>
      </li>)}
    </ol>
  )
}

function ClaimEvidence({ claims }: { claims: AgentResponse['claims'] }) {
  return (
    <div className="claims">
      <h3>逐条主张</h3>
      <ol className="claim-list" aria-label="逐条主张">
        {claims.map((claim) => (
          <li key={claim.claim_id}>
            <span className="claim-id">{claim.claim_id}</span>
            <div>
              <p>{claim.text}</p>
              <code>引用 {String(claim.citation_index + 1).padStart(2, '0')} · {claim.source_uri}</code>
            </div>
            <span className="claim-support" title={`support_score=${claim.verification.support_score}`}>
              {claim.verification.supported ? '支持' : '未支持'}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

function CustomerWorkspace() {
  const [message, setMessage] = useState('HTTP 429 响应里的 Retry-After 应该如何处理？')
  const [featureCode, setFeatureCode] = useState('')
  const [metricCode, setMetricCode] = useState('')
  const [sessionId] = useState(() => crypto.randomUUID())
  const [trace, setTrace] = useState<TraceEvent[]>([])
  const [result, setResult] = useState<AgentResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [stopped, setStopped] = useState(false)
  const [recoveryNote, setRecoveryNote] = useState('')
  const runIdRef = useRef<string | null>(null)
  const lastEventIdRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const confirmationKeyRef = useRef<string | null>(null)
  const lastActionRef = useRef<'confirm_ticket' | 'cancel_ticket' | undefined>(undefined)

  async function execute(confirmation?: 'confirm_ticket' | 'cancel_ticket') {
    setBusy(true)
    setStopped(false)
    setError('')
    setRecoveryNote('')
    runIdRef.current = null
    lastEventIdRef.current = null
    setTrace([])
    lastActionRef.current = confirmation
    const controller = new AbortController()
    abortRef.current = controller
    const idempotencyKey = confirmation === 'confirm_ticket'
      ? (confirmationKeyRef.current ?? crypto.randomUUID())
      : undefined
    if (confirmation === 'confirm_ticket') {
      confirmationKeyRef.current = idempotencyKey ?? null
    } else {
      confirmationKeyRef.current = null
    }
    const payload: Record<string, unknown> = {
      session_id: sessionId,
      message: confirmation ? (confirmation === 'confirm_ticket' ? '确认创建工单' : '取消创建工单') : message,
      context: {
        ...(featureCode ? { feature_code: featureCode } : {}),
        ...(metricCode ? { metric_code: metricCode } : {}),
      },
      ...(confirmation ? { confirmation } : {}),
    }
    try {
      await streamAgent(payload, {
        onProgress: (event) => setTrace((current) => [...current, event]),
        onEventId: (eventId) => {
          lastEventIdRef.current = eventId
          runIdRef.current = eventId.split(':')[0] ?? null
        },
        onResult: (response) => {
          setResult(response)
          confirmationKeyRef.current = null
        },
      }, idempotencyKey, controller.signal)
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === 'AbortError') {
        setStopped(true)
        setError('已停止等待。服务器可能已经完成本次运行；重试确认会复用同一幂等键。')
      } else {
        const runId = runIdRef.current
        if (runId) {
          try {
            await recoverRun(runId)
            setRecoveryNote('已从服务端恢复断线前的事件。')
            return
          } catch (recoveryError) {
            setError(messageFrom(recoveryError))
            return
          }
        }
        setError(messageFrom(caught))
      }
    } finally {
      abortRef.current = null
      setBusy(false)
    }
  }

  async function recoverRun(runId: string) {
    const response = await listRunEvents(runId)
    const progressEvents = response.items
      .filter((event) => event.event === 'progress')
      .map((event) => event.payload as unknown as TraceEvent)
    setTrace(progressEvents)
    const resultEvent = [...response.items].reverse().find((event) => event.event === 'result')
    if (resultEvent) {
      setResult(resultEvent.payload as unknown as AgentResponse)
      confirmationKeyRef.current = null
      return
    }
    const resumed = await resumeAgentRun(runId)
    setResult(resumed)
    confirmationKeyRef.current = null
  }


  function stop() {
    abortRef.current?.abort()
  }

  function retry() {
    void execute(lastActionRef.current)
  }

  return (
    <div className="workspace-grid customer-grid">
      <section className="panel compose-panel">
        <p className="eyebrow">客户问题</p>
        <h2>描述你遇到的问题</h2>
        <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={6} />
        <details><summary>补充结构化上下文</summary><div className="field-grid">
          <label>功能编码<input value={featureCode} onChange={(event) => setFeatureCode(event.target.value)} placeholder="bulk_export" /></label>
          <label>指标编码<input value={metricCode} onChange={(event) => setMetricCode(event.target.value)} placeholder="api_calls" /></label>
        </div></details>
        <div className="button-row">
          <button className="primary" onClick={() => execute()} disabled={busy || message.length < 2}>{busy ? 'Agent 正在诊断…' : '开始诊断'}</button>
          {busy && <button className="ghost" onClick={stop}>停止等待</button>}
          {!busy && stopped && <button className="ghost" onClick={retry}>重试上一步</button>}
        </div>
        {error && <p className="error-banner" role="alert">{error}</p>}
        {recoveryNote && <p className="muted" role="status">{recoveryNote}</p>}
        <div className="session-note">Session · {sessionId.slice(0, 8)}</div>
      </section>
      <section className="panel result-panel">
        <div className="panel-heading"><div><p className="eyebrow">受控响应</p><h2>诊断结果</h2></div>{result && <span className={`risk ${result.risk_level}`}>{result.risk_level}</span>}</div>
        {!result && !trace.length && <div className="empty-state">提交问题后，这里会展示回答、证据和逐节点执行轨迹。</div>}
        {result && <>
          <div className={`outcome ${result.outcome}`}><span>{result.outcome}</span><strong>{result.intent}</strong></div>
          <p className="answer">{result.message}</p>
          {result.ticket_draft && <div className="ticket-draft"><p className="eyebrow">写操作确认</p><h3>{result.ticket_draft.summary}</h3><p>{result.ticket_draft.description}</p><div className="button-row"><button className="primary" onClick={() => execute('confirm_ticket')} disabled={busy}>确认创建工单</button><button className="ghost" onClick={() => execute('cancel_ticket')} disabled={busy}>取消</button></div></div>}
          {!!result.claims?.length && <ClaimEvidence claims={result.claims} />}
          {!!result.citations.length && <div className="evidence"><h3>引用证据</h3>{result.citations.map((citation, index) => <article key={citation.chunk_id}><span>{String(index + 1).padStart(2, '0')}</span><div><strong>{citation.title}</strong><p>{citation.excerpt}</p><code>{citation.source_uri}</code></div></article>)}</div>}
          <div className="run-meta"><span>Trace {result.trace_id.slice(0, 10)}</span><span>{result.model_usage.model_calls} model calls</span><span>{result.model_usage.total_tokens} tokens</span></div>
        </>}
      </section>
      <aside className="panel trace-panel"><p className="eyebrow">Live trace</p><h2>执行轨迹</h2>{trace.length ? <TraceTimeline events={trace} /> : <p className="muted">等待节点事件…</p>}</aside>
    </div>
  )
}

const TICKET_STATUSES: TicketStatus[] = [
  'open',
  'triaged',
  'in_progress',
  'waiting_customer',
  'resolved',
  'closed',
]

const NEXT_STATUS: Partial<Record<TicketStatus, TicketStatus[]>> = {
  triaged: ['in_progress'],
  in_progress: ['waiting_customer', 'resolved'],
  waiting_customer: ['in_progress', 'resolved'],
  resolved: ['closed', 'in_progress'],
}

function SupportWorkspace({ user }: { user: CurrentUser }) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [activeQuery, setActiveQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<TicketStatus | ''>('')
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const nextCursorRef = useRef<string | null>(null)
  const selected = useMemo(() => tickets.find((ticket) => ticket.id === selectedId) ?? tickets[0] ?? null, [tickets, selectedId])

  const loadTickets = useCallback(async (append = false) => {
    try {
      const response = await listTickets({
        status: statusFilter || undefined,
        q: activeQuery || undefined,
        cursor: append ? nextCursorRef.current ?? undefined : undefined,
      })
      setTickets((current) => append ? [...current, ...response.items] : response.items)
      nextCursorRef.current = response.next_cursor
      setNextCursor(response.next_cursor)
      setTotal(response.total)
    } catch (caught) {
      setError(messageFrom(caught))
    }
  }, [activeQuery, statusFilter])

  useEffect(() => {
    void loadTickets()
  }, [loadTickets])

  function applySearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setActiveQuery(searchInput.trim())
  }

  function replace(ticket: Ticket) {
    setTickets((current) => current.map((item) => item.id === ticket.id ? ticket : item))
  }

  async function mutate(action: () => Promise<Ticket>) {
    setBusy(true); setError('')
    try { replace(await action()) } catch (caught) { setError(messageFrom(caught)); await loadTickets() } finally { setBusy(false) }
  }

  return (
    <div className="support-layout">
      <aside className="queue-panel"><div className="queue-heading"><div><p className="eyebrow">Human handoff</p><h2>工单队列</h2></div><button className="icon-button" onClick={() => void loadTickets()} aria-label="刷新工单">↻</button></div>
        <form className="queue-filters" onSubmit={applySearch}>
          <input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="搜索工单号或摘要" aria-label="搜索工单" />
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as TicketStatus | '')} aria-label="工单状态">
            <option value="">全部状态</option>
            {TICKET_STATUSES.map((status) => <option key={status} value={status}>{status}</option>)}
          </select>
        </form>
        <div className="queue-count">{tickets.length} / {total} 个工单</div>
        <div className="ticket-list">{tickets.map((ticket) => <button key={ticket.id} className={selected?.id === ticket.id ? 'ticket-row active' : 'ticket-row'} onClick={() => setSelectedId(ticket.id)}><div><strong>{ticket.public_code}</strong><span className={`severity ${ticket.severity}`}>{ticket.severity}</span></div><p>{ticket.summary}</p><small>{ticket.status.replace('_', ' ')}</small></button>)}</div>
        {nextCursor && <button className="ghost queue-more" onClick={() => void loadTickets(true)}>加载更多</button>}
      </aside>
      <main className="ticket-detail">
        {error && <p className="error-banner" role="alert">{error}</p>}
        {!selected ? <div className="empty-state">当前没有工单。客户确认升级后，工单会出现在这里。</div> : <>
          <div className="ticket-title"><div><p className="eyebrow">{selected.public_code}</p><h1>{selected.summary}</h1></div><span className={`status-pill ${selected.status}`}>{selected.status}</span></div>
          <div className="ticket-meta"><span>{selected.category}</span><span>{selected.severity}</span><span>v{selected.version}</span><span>{new Date(selected.created_at).toLocaleString()}</span></div>
          <section className="detail-card"><h3>问题描述</h3><p>{selected.description}</p></section>
          <section className="detail-card"><h3>诊断上下文</h3><pre>{JSON.stringify(selected.diagnostic_context, null, 2)}</pre></section>
          <section className="detail-card actions-card"><h3>人工处理</h3>
            {!selected.assignee_id && selected.status === 'open' && <button className="primary" disabled={busy} onClick={() => mutate(() => claimTicket(selected))}>认领并分诊</button>}
            {selected.assignee_id === user.id && (NEXT_STATUS[selected.status] ?? []).map((status) => <button key={status} className="ghost" disabled={busy} onClick={() => mutate(() => transitionTicket(selected, status, `人工处理：转为 ${status}`))}>转为 {status}</button>)}
            {selected.assignee_id && selected.assignee_id !== user.id && <p className="muted">该工单已由其他支持人员认领。</p>}
          </section>
          <section className="detail-card"><h3>状态轨迹</h3>{selected.transitions.length ? <ol className="transition-list">{selected.transitions.map((transition) => <li key={transition.id}><strong>{transition.from_status} → {transition.to_status}</strong><span>{transition.reason}</span></li>)}</ol> : <p className="muted">尚无人工状态变更。</p>}</section>
          {selected.agent_run_id && <FeedbackForm ticket={selected} />}
        </>}
      </main>
    </div>
  )
}

function FeedbackForm({ ticket }: { ticket: Ticket }) {
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    try {
      await submitFeedback(ticket, {
        agent_run_id: ticket.agent_run_id,
        disposition: data.get('disposition'),
        resolution_category: ticket.category,
        knowledge_gap: data.get('knowledge_gap') === 'on',
        comment: data.get('comment') || null,
      })
      setSent(true)
    } catch (caught) { setError(messageFrom(caught)) }
  }
  return <form className="detail-card feedback-form" onSubmit={submit}><h3>反馈回流</h3>{sent ? <p className="success-banner">反馈已记录，可用于后续离线评测。</p> : <><label>Agent 建议<select name="disposition"><option value="accepted">直接采纳</option><option value="edited">修改后采纳</option><option value="rejected">拒绝</option></select></label><label>复盘说明<textarea name="comment" rows={3} /></label><label className="check"><input type="checkbox" name="knowledge_gap" />存在知识缺口</label><button className="primary">提交反馈</button></>}{error && <p className="error-banner">{error}</p>}</form>
}

export default function App() {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [restoring, setRestoring] = useState(true)

  useEffect(() => {
    restoreSession()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setRestoring(false))
  }, [])

  if (restoring) return <div className="splash">恢复安全会话…</div>
  if (!user) return <Login onAuthenticated={setUser} />
  return <div className="app-shell"><header className="topbar"><div className="brand"><span>SP</span><div><strong>SupportPilot</strong><small>Evidence-led support</small></div></div><div className="user-chip"><div><strong>{user.display_name}</strong><small>{user.role}</small></div><button onClick={() => { void logout().catch(() => undefined).finally(() => setUser(null)) }}>退出</button><button title="撤销本账号的全部会话" onClick={() => { void logoutAll().catch(() => undefined).finally(() => setUser(null)) }}>登出所有设备</button></div></header>{user.role === 'support_agent' ? <SupportWorkspace user={user} /> : <CustomerWorkspace />}</div>
}
