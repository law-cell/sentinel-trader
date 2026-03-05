import { useEffect, useState, useCallback } from 'react'
import { TrendingUp, TrendingDown, Wallet, DollarSign, Zap, Bell } from 'lucide-react'
import { fetchAccount, fetchPositions, fetchHistory } from '../api/client'
import type { AccountSummaryResponse, PositionResponse, TriggerEvent } from '../types/api'

// ── helpers ──────────────────────────────────────────────────────────────────

function fmt(value: number | null | undefined, decimals = 2): string {
  if (value == null) return '—'
  return value.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

function fmtCurrency(value: number | null | undefined): string {
  if (value == null) return '—'
  return '$' + fmt(value)
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return `${h}h ago`
}

// ── sub-components ────────────────────────────────────────────────────────────

interface MetricCardProps {
  label: string
  value: string
  icon: React.ReactNode
  positive?: boolean | null
  subtitle?: string
}

function MetricCard({ label, value, icon, positive, subtitle }: MetricCardProps) {
  const valueColor =
    positive === true ? 'var(--green)' :
    positive === false ? 'var(--red)' :
    'var(--text)'

  return (
    <div
      style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12 }}
      className="p-5 flex flex-col gap-3"
    >
      <div className="flex items-center justify-between">
        <span style={{ color: 'var(--muted)', fontSize: 13 }}>{label}</span>
        <span style={{ color: 'var(--muted)' }}>{icon}</span>
      </div>
      <span className="mono text-2xl font-semibold" style={{ color: valueColor }}>
        {value}
      </span>
      {subtitle && (
        <span style={{ color: 'var(--muted)', fontSize: 12 }}>{subtitle}</span>
      )}
    </div>
  )
}

// ── main component ────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [account, setAccount] = useState<AccountSummaryResponse | null>(null)
  const [positions, setPositions] = useState<PositionResponse[]>([])
  const [history, setHistory] = useState<TriggerEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  const load = useCallback(async () => {
    try {
      const [acct, pos, hist] = await Promise.all([
        fetchAccount(),
        fetchPositions(),
        fetchHistory(10),
      ])
      setAccount(acct)
      setPositions(pos)
      setHistory(hist)
      setError(null)
      setLastRefresh(new Date())
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to fetch data'
      setError(msg)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [load])

  const s = account?.summary

  const unrealizedPnL = s?.UnrealizedPnL ?? null
  const pnlPositive = unrealizedPnL == null ? null : unrealizedPnL >= 0

  return (
    <div className="flex flex-col gap-6 max-w-6xl">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>Dashboard</h1>
          {account && (
            <span className="text-xs mono" style={{ color: 'var(--muted)' }}>
              Account: {account.account}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span style={{ color: 'var(--muted)', fontSize: 12 }}>
            Updated {lastRefresh.toLocaleTimeString()}
          </span>
          <button
            onClick={load}
            style={{
              background: 'var(--card)',
              border: '1px solid var(--border)',
              color: 'var(--muted)',
              borderRadius: 8,
              padding: '4px 12px',
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div
          style={{ background: 'rgba(255,68,68,0.1)', border: '1px solid var(--red)', borderRadius: 8 }}
          className="px-4 py-3 text-sm"
        >
          <span style={{ color: 'var(--red)' }}>API Error: {error}</span>
          <span style={{ color: 'var(--muted)', marginLeft: 8 }}>— Make sure the API server is running</span>
        </div>
      )}

      {/* Account summary cards */}
      <section>
        <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--muted)' }}>
          ACCOUNT SUMMARY
        </h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <MetricCard
            label="Net Liquidation"
            value={fmtCurrency(s?.NetLiquidation)}
            icon={<Wallet size={16} />}
          />
          <MetricCard
            label="Cash Balance"
            value={fmtCurrency(s?.TotalCashValue)}
            icon={<DollarSign size={16} />}
          />
          <MetricCard
            label="Buying Power"
            value={fmtCurrency(s?.BuyingPower)}
            icon={<Zap size={16} />}
          />
          <MetricCard
            label="Unrealized P&L"
            value={fmtCurrency(s?.UnrealizedPnL)}
            icon={pnlPositive ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
            positive={pnlPositive}
          />
        </div>
      </section>

      {/* Positions + Alerts in a 2-col grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">

        {/* Positions table — 3 cols */}
        <section
          style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12 }}
          className="lg:col-span-3 overflow-hidden"
        >
          <div className="px-5 py-4 flex items-center justify-between" style={{ borderBottom: '1px solid var(--border)' }}>
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>Open Positions</h2>
            <span className="text-xs mono" style={{ color: 'var(--muted)' }}>{positions.length} positions</span>
          </div>

          {positions.length === 0 ? (
            <div className="px-5 py-8 text-center text-sm" style={{ color: 'var(--muted)' }}>
              No open positions
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Symbol', 'Type', 'Exchange', 'Qty', 'Avg Cost'].map(h => (
                    <th key={h} className="px-5 py-3 text-left font-medium" style={{ color: 'var(--muted)', fontSize: 11 }}>
                      {h.toUpperCase()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => {
                  const isLong = p.position > 0
                  return (
                    <tr
                      key={i}
                      style={{ borderBottom: '1px solid var(--border)' }}
                      className="hover:bg-white/5 transition-colors"
                    >
                      <td className="px-5 py-3 font-semibold mono" style={{ color: 'var(--text)' }}>
                        {p.symbol}
                      </td>
                      <td className="px-5 py-3" style={{ color: 'var(--muted)' }}>{p.sec_type}</td>
                      <td className="px-5 py-3" style={{ color: 'var(--muted)' }}>{p.exchange || '—'}</td>
                      <td className="px-5 py-3 mono font-medium" style={{ color: isLong ? 'var(--green)' : 'var(--red)' }}>
                        {isLong ? '+' : ''}{fmt(p.position, 0)}
                      </td>
                      <td className="px-5 py-3 mono" style={{ color: 'var(--text)' }}>
                        {fmtCurrency(p.avg_cost)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </section>

        {/* Recent alerts timeline — 2 cols */}
        <section
          style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12 }}
          className="lg:col-span-2 overflow-hidden"
        >
          <div className="px-5 py-4 flex items-center gap-2" style={{ borderBottom: '1px solid var(--border)' }}>
            <Bell size={14} style={{ color: 'var(--muted)' }} />
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>Recent Alerts</h2>
          </div>

          {history.length === 0 ? (
            <div className="px-5 py-8 text-center text-sm" style={{ color: 'var(--muted)' }}>
              No alerts yet
            </div>
          ) : (
            <div className="flex flex-col">
              {history.map((evt, i) => (
                <div
                  key={i}
                  className="flex gap-3 px-5 py-4"
                  style={{ borderBottom: i < history.length - 1 ? '1px solid var(--border)' : 'none' }}
                >
                  {/* Timeline dot */}
                  <div className="flex flex-col items-center gap-1 pt-1 flex-shrink-0">
                    <div
                      style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--green)', flexShrink: 0 }}
                    />
                    {i < history.length - 1 && (
                      <div style={{ width: 1, flex: 1, background: 'var(--border)', minHeight: 16 }} />
                    )}
                  </div>

                  {/* Content */}
                  <div className="flex flex-col gap-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold mono text-xs" style={{ color: 'var(--green)' }}>
                        {evt.symbol}
                      </span>
                      <span className="mono text-xs" style={{ color: 'var(--muted)' }}>
                        ${fmt(evt.price)}
                      </span>
                    </div>
                    <span className="text-xs leading-snug truncate" style={{ color: 'var(--text)' }}>
                      {evt.rule_name}
                    </span>
                    <span className="text-xs mono" style={{ color: 'var(--muted)' }}>
                      {relativeTime(evt.timestamp)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
