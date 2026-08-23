import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowLeft, RefreshCw, Search, Sliders } from 'lucide-react'
import './AdminPage.css'

export interface AdminOverview {
  total_sessions: number
  total_messages: number
  total_leads: number
  consented_leads: number
  conversion_rate: number
  avg_completeness: number
  avg_messages_per_session: number
  avg_messages_per_lead: number
  captured: Record<string, number>
}

export interface AdminLead {
  id: number
  session_id: string
  name: string | null
  position: string | null
  company: string | null
  phone: string | null
  email: string | null
  consent: boolean | null
  completeness: number
  message_count: number
  created_at: string | null
  updated_at: string | null
}

export interface AdminAnalytics {
  generated_at: string | null
  overview: AdminOverview
  leads: AdminLead[]
  timeline: { date: string; leads: number; messages: number }[]
  hourly: { hour: number; leads: number }[]
  companies: { name: string; count: number }[]
  positions: { name: string; count: number }[]
  field_labels: Record<string, string>
}

async function fetchAnalytics(): Promise<AdminAnalytics> {
  const res = await fetch('/api/admin/analytics/')
  if (!res.ok) throw new Error(`Request failed: ${res.status}`)
  return (await res.json()) as AdminAnalytics
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString()
}

function maxOf(values: number[]): number {
  return values.length ? Math.max(...values) : 0
}

function BarList({ items, empty }: { items: { name: string; count: number }[]; empty: string }) {
  const max = maxOf(items.map((i) => i.count))
  if (!items.length) return <p className="empty">{empty}</p>
  return (
    <ul className="bar-list">
      {items.map((item) => (
        <li key={item.name} className="bar-row">
          <span className="bar-label" title={item.name}>{item.name || '(blank)'}</span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${max ? (item.count / max) * 100 : 0}%` }} />
          </span>
          <span className="bar-value">{item.count}</span>
        </li>
      ))}
    </ul>
  )
}

function AdminPage() {
  const [data, setData] = useState<AdminAnalytics | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [query, setQuery] = useState('')

  const load = useCallback(async () => {
    try {
      const payload = await fetchAnalytics()
      setData(payload)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    const initial = setTimeout(() => void load(), 0)
    const timer = setInterval(() => void load(), 60_000)
    return () => {
      clearTimeout(initial)
      clearInterval(timer)
    }
  }, [load])

  const filtered = useMemo(() => {
    const leads = data?.leads ?? []
    const q = query.trim().toLowerCase()
    if (!q) return leads
    return leads.filter((lead) =>
      [lead.name, lead.position, lead.company, lead.phone, lead.email, lead.session_id]
        .some((v) => v && v.toLowerCase().includes(q)),
    )
  }, [data, query])

  const captures = useMemo(() => {
    const labels = data?.field_labels ?? {}
    return Object.entries(data?.overview.captured ?? {}).map(([key, count]) => ({
      key,
      label: labels[key] ?? key,
      count,
      pct: data && data.overview.total_leads ? Math.round((count / data.overview.total_leads) * 100) : 0,
    }))
  }, [data])

  const timelineMax = data ? maxOf(data.timeline.flatMap((d) => [d.leads, d.messages])) : 0
  const hourlyMax = data ? maxOf(data.hourly.map((h) => h.leads)) : 0

  if (loading && !data) {
    return (
      <div className="admin-page">
        <p className="admin-state">Loading analytics…</p>
      </div>
    )
  }

  return (
    <div className="admin-page">
      <header className="admin-header">
        <a className="admin-nav-link" href="/">
          <ArrowLeft size={16} /> Back to Mina
        </a>
        <h1>Mina AI — Admin Analytics</h1>
        <div className="admin-header-actions">
          <a
            className="admin-nav-link dev-link"
            href="/dev"
            title="Configure online models, API keys, endpoints and reasoning parameters"
          >
            <Sliders size={15} /> Developer Settings
          </a>
          {data?.generated_at && (
            <span className="admin-updated">Updated {fmtDateTime(data.generated_at)}</span>
          )}
          <button
            type="button"
            className="refresh-btn"
            onClick={() => {
              setRefreshing(true)
              void load()
            }}
            disabled={refreshing}
            title="Refresh analytics"
          >
            <RefreshCw size={15} className={refreshing ? 'spin' : ''} />
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      {error && <div className="admin-error" role="alert">Failed to load analytics: {error}</div>}

      {data && (
        <>
          <section className="admin-section">
            <h2>Overview</h2>
            <div className="stat-grid">
              <div className="stat-card">
                <span className="stat-value">{data.overview.total_sessions}</span>
                <span className="stat-label">Sessions</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{data.overview.total_messages}</span>
                <span className="stat-label">Messages</span>
              </div>
              <div className="stat-card accent">
                <span className="stat-value">{data.overview.total_leads}</span>
                <span className="stat-label">Captured People</span>
              </div>
              <div className="stat-card">
                <span className="stat-value green">{data.overview.consented_leads}</span>
                <span className="stat-label">With Consent</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{data.overview.conversion_rate}%</span>
                <span className="stat-label">Lead Rate / Session</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{data.overview.avg_completeness}%</span>
                <span className="stat-label">Avg Profile Completeness</span>
              </div>
            </div>
            <div className="side-stats">
              <span>Avg messages per session: <b>{data.overview.avg_messages_per_session}</b></span>
              <span>Avg messages per captured person: <b>{data.overview.avg_messages_per_lead}</b></span>
            </div>
          </section>

          <section className="admin-section">
            <h2>Info Capture Rates</h2>
            {data.overview.total_leads === 0 ? (
              <p className="empty">No people captured yet — leads appear when Mina saves contact info during sessions.</p>
            ) : (
              <ul className="bar-list">
                {captures.map((c) => (
                  <li key={c.key} className="bar-row">
                    <span className="bar-label">{c.label}</span>
                    <span className="bar-track">
                      <span className="bar-fill" style={{ width: `${c.pct}%` }} />
                    </span>
                    <span className="bar-value">{c.count} ({c.pct}%)</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="admin-section">
            <h2>Captured People ({filtered.length})</h2>
            <div className="table-tools">
              <div className="search-box">
                <Search size={14} />
                <input
                  type="search"
                  placeholder="Search name, company, phone, email…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
            </div>
            {filtered.length === 0 ? (
              <p className="empty">No matching people found.</p>
            ) : (
              <div className="table-wrap">
                <table className="leads-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Position</th>
                      <th>Company</th>
                      <th>Phone</th>
                      <th>Email</th>
                      <th>Consent</th>
                      <th>Profile</th>
                      <th>Msgs</th>
                      <th>Last Active</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((lead) => (
                      <tr key={lead.id}>
                        <td className="cell-strong">{lead.name ?? '—'}</td>
                        <td>{lead.position ?? '—'}</td>
                        <td>{lead.company ?? '—'}</td>
                        <td>{lead.phone ?? '—'}</td>
                        <td>{lead.email ?? '—'}</td>
                        <td>
                          {lead.consent === null ? (
                            <span className="pill pill-unknown">n/a</span>
                          ) : lead.consent ? (
                            <span className="pill pill-yes">yes</span>
                          ) : (
                            <span className="pill pill-no">no</span>
                          )}
                        </td>
                        <td>
                          <span className="mini-bar" title={`${lead.completeness}% of fields captured`}>
                            <span className="mini-bar-fill" style={{ width: `${lead.completeness}%` }} />
                          </span>
                          <span className="mini-bar-num">{lead.completeness}%</span>
                        </td>
                        <td>{lead.message_count}</td>
                        <td className="cell-muted" title={`Session: ${lead.session_id}`}>{fmtDateTime(lead.updated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <div className="admin-columns">
            <section className="admin-section">
              <h2>Timeline — Last 30 Days</h2>
              {timelineMax === 0 ? (
                <p className="empty">No activity in the last 30 days.</p>
              ) : (
                <div className="timeline-chart">
                  {data.timeline.map((day) => (
                    <div className="timeline-col" key={day.date} title={`${day.date} — ${day.leads} people, ${day.messages} messages`}>
                      <div className="timeline-tracks">
                        <span className="timeline-bar lead" style={{ height: `${(day.leads / timelineMax) * 100}%` }} />
                        <span className="timeline-bar msg" style={{ height: `${(day.messages / timelineMax) * 100}%` }} />
                      </div>
                      <span className="timeline-date">{day.date.slice(5)}</span>
                    </div>
                  ))}
                </div>
              )}
              <p className="legend"><span className="legend-dot lead" /> People captured <span className="legend-dot msg" /> Messages</p>
            </section>

            <section className="admin-section">
              <h2>Peak Capture Hours</h2>
              {hourlyMax === 0 ? (
                <p className="empty">Not enough data yet.</p>
              ) : (
                <div className="hourly-chart">
                  {data.hourly.map((h) => (
                    <div className="hourly-col" key={h.hour} title={`${h.hour}:00 — ${h.leads} people`}>
                      <span className="hourly-bar" style={{ height: `${(h.leads / hourlyMax) * 100}%` }} />
                      <span className="hourly-label">{h.hour}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          <div className="admin-columns">
            <section className="admin-section">
              <h2>Top Companies</h2>
              <BarList items={data.companies} empty="No companies captured yet." />
            </section>
            <section className="admin-section">
              <h2>Top Positions</h2>
              <BarList items={data.positions} empty="No positions captured yet." />
            </section>
          </div>
        </>
      )}
    </div>
  )
}

export default AdminPage