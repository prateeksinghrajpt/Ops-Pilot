import { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, AlertTriangle, ArrowUpRight, Bot, CheckCircle2, ChevronRight, CircleDot, Clock3, Cpu, Database, FileSearch, Gauge, LoaderCircle, LogOut, Plus, RefreshCw, ShieldCheck, Siren, Sparkles, X } from 'lucide-react'
import { api, clearAccessToken, getAccessToken } from './api'
import AuthScreen from './AuthScreen'

const scenarios = [
  { value: 'http_5xx_spike', label: 'HTTP 5xx error spike', detail: 'Elevated server errors and slow upstream dependency' },
  { value: 'database_latency', label: 'Database latency', detail: 'Slow queries and connection pool saturation' },
  { value: 'memory_pressure', label: 'Memory pressure', detail: 'High memory use and repeated worker restarts' },
  { value: 'deployment_regression', label: 'Deployment regression', detail: 'Latency spike after a recent release' },
]
const severityClass = (value) => `severity ${String(value || 'medium').toLowerCase()}`
const pretty = (value) => String(value || '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())
const timeAgo = (value) => {
  if (!value) return '—'
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`
  return `${Math.floor(minutes / 1440)}d ago`
}

function App() {
  const [incidents, setIncidents] = useState([])
  const [stats, setStats] = useState({ total_incidents: 0, open_incidents: 0, investigating_incidents: 0, critical_active: 0 })
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [modal, setModal] = useState(false)
  const [error, setError] = useState('')
  const [scenario, setScenario] = useState('http_5xx_spike')
  const [service, setService] = useState('checkout-service')
  const [severity, setSeverity] = useState('high')
  const [toast, setToast] = useState('')
  const [user, setUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [adminView, setAdminView] = useState(false)
  const [accessRequests, setAccessRequests] = useState([])

  const requestAccess = async () => {
    setBusy(true)
    try {
      await api.requestAccess()
      setToast('Access request sent to the administrator.')
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const loadAccessRequests = async () => {
    setBusy(true)
    try {
      setAccessRequests(await api.accessRequests())
      setError('')
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const openAdminDashboard = () => {
    setAdminView(true)
    loadAccessRequests()
  }

  const resolveAccessRequest = async (request, approved) => {
    setBusy(true)
    try {
      if (approved) await api.grantAccess(request.id)
      else await api.rejectAccess(request.id)
      await loadAccessRequests()
      setToast(approved ? `Granted one use to ${request.requester_email}.` : `Rejected ${request.requester_email}'s request.`)
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const refresh = useCallback(async () => {
    try {
      const [summary, rows] = await Promise.all([api.dashboard(), api.incidents()])
      setStats(summary)
      setIncidents(rows)
      setError('')
      if (selected?.id) {
        const fresh = rows.find(item => item.id === selected.id)
        if (fresh) setSelected(fresh)
      }
    } catch (e) {
      setError(`${e.message}. Is the FastAPI backend running on port 8000?`)
    } finally { setLoading(false) }
  }, [selected?.id])

  useEffect(() => {
    if (!getAccessToken()) {
      setAuthLoading(false)
      return
    }
    api.me().then(setUser).catch(clearAccessToken).finally(() => setAuthLoading(false))
  }, [])
  useEffect(() => { if (user) refresh() }, [user])
  useEffect(() => {
    if (!user) return undefined
    const timer = setInterval(refresh, 15000)
    return () => clearInterval(timer)
  }, [refresh, user])

  const logout = () => {
    clearAccessToken()
    setUser(null)
    setIncidents([])
    setSelected(null)
    setAdminView(false)
  }

  const openIncident = async (item) => {
    setSelected(item)
    try { setSelected(await api.incident(item.id)) } catch (e) { setError(e.message) }
  }

  const simulate = async (event) => {
    event.preventDefault()
    setBusy(true)
    try {
      const created = await api.simulate({ scenario, service_name: service, severity })
      setModal(false)
      setToast('Incident created. Start an investigation to generate a report.')
      await refresh()
      await openIncident(created)
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const investigate = async (id) => {
    setBusy(true)
    try {
      const updated = await api.investigate(id)
      setSelected(updated)
      setUser(await api.me())
      setToast('Investigation completed.')
      await refresh()
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const approve = async (id) => {
    setBusy(true)
    try {
      const updated = await api.approve(id, { approved_by: 'portfolio-demo-user', note: 'Reviewed in OpsPilot demo UI.' })
      setSelected(updated)
      setToast('Approval recorded. No infrastructure action was executed.')
      await refresh()
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const current = selected || incidents[0] || null
  const criticalPercent = stats.total_incidents ? Math.round((stats.critical_active / stats.total_incidents) * 100) : 0

  if (authLoading) return <div className="auth-loading"><LoaderCircle className="spin" size={24}/></div>
  if (!user) return <AuthScreen onAuthenticated={setUser}/>

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Activity size={21}/></div><div><b>OpsPilot</b><span>INCIDENT INTELLIGENCE</span></div></div>
      <div className="workspace"><div className="workspace-icon">OC</div><div><b>Orbit Commerce</b><span>Engineering workspace</span></div><ChevronRight size={15}/></div>
      <div className="nav-label">WORKSPACE</div>
      <button className={`nav-item ${!adminView ? 'active' : ''}`} onClick={() => setAdminView(false)}><Gauge size={17}/> Overview <span className="nav-dot"/></button>
      <button className="nav-item" onClick={() => setSelected(null)}><Siren size={17}/> Incidents <span className="nav-count">{stats.open_incidents}</span></button>
      <button className="nav-item" onClick={() => setToast('Service map is a planned extension of this MVP.')}><Activity size={17}/> Service map</button>
      <button className="nav-item" onClick={() => setToast('Telemetry integrations are planned; current signals are simulated.')}><Database size={17}/> Telemetry sources</button>
      <div className="nav-label second">OPERATIONS</div>
      <button className="nav-item" onClick={() => setToast('Investigation history is available by selecting an incident.')}><Bot size={17}/> AI investigations</button>
      <button className="nav-item" onClick={() => setToast('Audit and settings pages are planned.')}><ShieldCheck size={17}/> Audit & approvals</button>
      {user.is_admin && <><div className="nav-label second">ADMINISTRATION</div><button className={`nav-item ${adminView ? 'active' : ''}`} onClick={openAdminDashboard}><ShieldCheck size={17}/> Access requests</button></>}
      <div className="sidebar-bottom"><div className="online"><span/> API connection</div><div className="user-card"><div className="avatar">{user.email.slice(0, 2).toUpperCase()}</div><div><b>{user.email}</b><span>Authenticated workspace</span></div><button className="logout-btn" title="Sign out" onClick={logout}><LogOut size={15}/></button></div></div>
    </aside>

    <main className="main">
      <header className="topbar"><div className="breadcrumbs">Workspace <ChevronRight size={14}/> <b>{adminView ? 'Admin access requests' : 'Overview'}</b></div><div className="top-actions"><span className="env-pill"><span/> SIMULATED ENVIRONMENT</span>{adminView ? <button className="primary-btn" disabled={busy} onClick={loadAccessRequests}><RefreshCw size={17}/> Refresh requests</button> : <><button className="icon-btn" title="Refresh data" onClick={refresh}><RefreshCw size={17}/></button><button className="primary-btn" disabled={!user.is_admin && user.access_uses_remaining < 1} onClick={() => setModal(true)}><Plus size={17}/> Simulate incident</button></>}</div></header>
      <div className="content">
        {error && <div className="error-banner"><AlertTriangle size={17}/><span>{error}</span><button onClick={() => setError('')}><X size={16}/></button></div>}
        {toast && <div className="toast"><CheckCircle2 size={16}/><span>{toast}</span><button onClick={() => setToast('')}><X size={15}/></button></div>}
        {adminView ? <AdminDashboard requests={accessRequests} busy={busy} onResolve={resolveAccessRequest}/> : <>
        <div className="page-heading"><div><div className="eyebrow"><span className="pulse"/> LIVE OPERATIONS OVERVIEW</div><h1>Good evening, Engineer <span>✦</span></h1><p>Here’s what’s happening across your services right now.</p></div><div className="updated"><Clock3 size={14}/> Auto-refreshes every 15 seconds</div></div>

        {!user.is_admin && user.access_uses_remaining < 1 && <div className="error-banner"><AlertTriangle size={17}/><span>Your free access has been used. Request another use from the administrator.</span><button className="text-btn" disabled={busy} onClick={requestAccess}>Request access</button></div>}

        <section className="stat-grid">
          <Stat icon={<Siren/>} label="Total incidents" value={stats.total_incidents} foot="Across all simulated services" tone="blue"/>
          <Stat icon={<AlertTriangle/>} label="Open incidents" value={stats.open_incidents} foot="Awaiting investigation" tone="orange"/>
          <Stat icon={<Bot/>} label="Investigating" value={stats.investigating_incidents} foot="AI analysis in progress" tone="purple"/>
          <Stat icon={<ShieldCheck/>} label="Critical active" value={stats.critical_active} foot={`${criticalPercent}% of all incidents`} tone="red"/>
        </section>

        <section className="section-grid">
          <div className="panel incident-panel">
            <div className="panel-head"><div><h2>Recent incidents</h2><p>Signals requiring engineering attention</p></div><button className="text-btn" onClick={refresh}>View all <ArrowUpRight size={14}/></button></div>
            {loading ? <div className="empty"><LoaderCircle className="spin"/> Loading incidents…</div> : incidents.length === 0 ? <div className="empty"><div className="empty-icon"><Siren/></div><b>No incidents yet</b><p>Simulate an incident to start an investigation.</p><button className="primary-btn" onClick={() => setModal(true)}><Plus size={16}/> Create demo incident</button></div> :
              <div className="incident-list">{incidents.map(item => <button key={item.id} className={`incident-row ${current?.id === item.id ? 'selected' : ''}`} onClick={() => openIncident(item)}>
                <div className={`incident-icon ${item.severity}`}><AlertTriangle size={17}/></div><div className="incident-info"><div className="incident-title">{item.title}<span className={severityClass(item.severity)}>{item.severity}</span></div><div className="incident-meta"><span>{item.service_name}</span><i/> <span>{timeAgo(item.created_at)}</span></div></div><div className={`status ${item.status}`}>{pretty(item.status)}</div><ChevronRight size={16} className="row-chevron"/>
              </button>)}</div>}
          </div>

          <div className="panel service-panel"><div className="panel-head"><div><h2>Service health</h2><p>Sample telemetry from the demo environment</p></div><span className="mini-live"><span/> DEMO</span></div>
            <div className="service-row"><div className="service-icon green"><Activity/></div><div className="service-copy"><b>API Gateway</b><span>Request routing</span></div><span className="health good"><i/> Healthy</span></div>
            <div className="service-row"><div className="service-icon orange"><Cpu/></div><div className="service-copy"><b>Checkout Service</b><span>Order processing</span></div><span className="health warn"><i/> Degraded</span></div>
            <div className="service-row"><div className="service-icon blue"><Database/></div><div className="service-copy"><b>PostgreSQL</b><span>Primary database</span></div><span className="health good"><i/> Healthy</span></div>
            <div className="service-row"><div className="service-icon purple"><Sparkles/></div><div className="service-copy"><b>AI Investigator</b><span>Root cause analysis</span></div><span className="health good"><i/> Available</span></div>
            <div className="service-foot"><span><span className="legend-dot good-dot"/> Healthy</span><span><span className="legend-dot warn-dot"/> Degraded</span><span><span className="legend-dot down-dot"/> Down</span></div>
          </div>
        </section>

        <section className="panel detail-panel">
          <div className="panel-head"><div><h2>Incident investigation</h2><p>{current ? `Review evidence and AI-generated findings for ${current.service_name}` : 'Select an incident to inspect its evidence and findings'}</p></div>{current && <span className={severityClass(current.severity)}>{current.severity} severity</span>}</div>
          {!current ? <div className="empty compact"><FileSearch size={27}/><p>Select an incident above or simulate one to get started.</p></div> : <div className="detail-grid">
            <div className="detail-main">
              <div className="incident-summary"><div className={`large-incident-icon ${current.severity}`}><AlertTriangle size={22}/></div><div><h3>{current.title}</h3><p>{current.summary || 'No summary supplied.'}</p><div className="summary-tags"><span><CircleDot size={12}/>{current.service_name}</span><span><Clock3 size={12}/>{new Date(current.created_at).toLocaleString()}</span><span className={`status ${current.status}`}>{pretty(current.status)}</span></div></div></div>
              {current.investigation ? <div className="finding-card"><div className="finding-heading"><div className="finding-icon"><Sparkles size={17}/></div><div><b>AI root-cause assessment</b><span>Model: {current.investigation.model}</span></div><div className="confidence"><b>{Math.round(current.investigation.confidence * 100)}%</b><span>confidence</span></div></div><p className="root-cause">{current.investigation.root_cause}</p><div className="impact"><b>Potential impact</b><p>{current.investigation.impact}</p></div><div className="actions-heading"><b>Recommended next steps</b><span>{current.investigation.recommended_actions?.length || 0} actions</span></div><ol className="action-list">{current.investigation.recommended_actions?.map((action, i) => <li key={i}><span>{i + 1}</span>{action}</li>)}</ol><div className="approval-note"><ShieldCheck size={16}/><span>{current.investigation.remediation_approved ? 'Approval recorded. No infrastructure action was executed.' : 'Recommendations are advisory. Engineer review is required.'}</span></div>{!current.investigation.remediation_approved && <button className="secondary-btn" disabled={busy} onClick={() => approve(current.id)}><ShieldCheck size={16}/> Record remediation approval</button>}</div> :
                <div className="investigation-cta"><div className="ai-orb"><Bot size={23}/></div><div><b>Ready to investigate</b><p>Analyze available evidence and generate a root-cause report with recommended next steps.</p></div><button className="primary-btn" disabled={busy} onClick={() => investigate(current.id)}>{busy ? <LoaderCircle className="spin" size={16}/> : <Sparkles size={16}/>} {busy ? 'Investigating…' : 'Run AI investigation'}</button></div>}
            </div>
            <div className="evidence-column"><div className="evidence-head"><div><h3>Collected evidence</h3><p>Signals attached to this incident</p></div><span className="evidence-count">{current.evidence?.length || 0}</span></div>{current.evidence?.length ? current.evidence.map(ev => <div className="evidence-item" key={ev.id}><div className={`evidence-dot ${ev.level}`}/><div className="evidence-content"><div className="evidence-top"><span>{pretty(ev.source)}</span><time>{timeAgo(ev.timestamp)}</time></div><p>{ev.message}</p>{ev.details && Object.keys(ev.details).length > 0 && <code>{Object.entries(ev.details).slice(0, 3).map(([k,v]) => `${k}: ${v}`).join(' · ')}</code>}</div></div>) : <div className="empty compact"><p>No evidence attached.</p></div>}</div>
          </div>}
        </section>
        <footer><span><Activity size={14}/> OpsPilot <b>v1.0.0</b></span><span>Portfolio MVP · Simulated telemetry · Human approval required</span></footer>
        </>}
      </div>
    </main>

    {modal && <div className="modal-backdrop" onClick={() => setModal(false)}><div className="modal" onClick={e => e.stopPropagation()}><div className="modal-head"><div><div className="modal-icon"><Plus size={19}/></div><h2>Simulate an incident</h2><p>Create a repeatable incident scenario for investigation.</p></div><button className="icon-btn" onClick={() => setModal(false)}><X size={18}/></button></div><form onSubmit={simulate}><label>Incident scenario<select value={scenario} onChange={e => setScenario(e.target.value)}>{scenarios.map(s => <option value={s.value} key={s.value}>{s.label}</option>)}</select></label><div className="scenario-hint">{scenarios.find(s => s.value === scenario)?.detail}</div><label>Service name<input value={service} onChange={e => setService(e.target.value)} minLength={2} maxLength={120} required/></label><label>Severity<select value={severity} onChange={e => setSeverity(e.target.value)}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label><div className="modal-actions"><button type="button" className="secondary-btn" onClick={() => setModal(false)}>Cancel</button><button className="primary-btn" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16}/> : <Plus size={16}/>} Create incident</button></div></form><div className="modal-foot"><ShieldCheck size={14}/> Simulation only — no real services are affected.</div></div></div>}
  </div>
}

function Stat({ icon, label, value, foot, tone }) {
  return <div className="stat-card"><div className={`stat-icon ${tone}`}>{icon}</div><div className="stat-label">{label}</div><div className="stat-value">{value}</div><div className="stat-foot"><span className={`stat-foot-dot ${tone}`}/>{foot}</div><div className={`stat-glow ${tone}`}/></div>
}

function AdminDashboard({ requests, busy, onResolve }) {
  const pending = requests.filter(request => request.status === 'pending')
  return <>
    <div className="page-heading"><div><div className="eyebrow"><span className="pulse"/> ADMINISTRATION</div><h1>Access requests</h1><p>Review requests and grant one additional app use when appropriate.</p></div><div className="updated"><ShieldCheck size={14}/> Admin-only area</div></div>
    <section className="panel incident-panel">
      <div className="panel-head"><div><h2>Pending requests</h2><p>{pending.length} request{pending.length === 1 ? '' : 's'} awaiting a decision</p></div></div>
      {pending.length === 0 ? <div className="empty compact"><ShieldCheck size={27}/><p>No pending access requests.</p></div> : <div className="incident-list">{pending.map(request => <div className="incident-row" key={request.id}><div className="incident-icon medium"><ShieldCheck size={17}/></div><div className="incident-info"><div className="incident-title">{request.requester_email}<span className="severity medium">Pending</span></div><div className="incident-meta"><span>Requested {new Date(request.created_at).toLocaleString()}</span></div></div><div className="modal-actions"><button className="secondary-btn" disabled={busy} onClick={() => onResolve(request, false)}>Reject</button><button className="primary-btn" disabled={busy} onClick={() => onResolve(request, true)}>Grant 1 use</button></div></div>)}</div>}
    </section>
  </>
}

export default App
