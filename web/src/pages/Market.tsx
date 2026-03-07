import { useEffect, useState, useRef, useCallback } from 'react'
import { X, TrendingUp, TrendingDown, Minus, RefreshCw, Search, Loader } from 'lucide-react'
import { fetchMarketData, searchSymbols } from '../api/client'
import type { MarketDataResponse, SymbolSearchResult } from '../types/api'

const DEFAULT_SYMBOLS = ['NVDA', 'SPY', 'TSLA']
const REFRESH_INTERVAL = 5000
const SEARCH_DEBOUNCE = 300

// ── helpers ───────────────────────────────────────────────────────────────────

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return '—'
  return v.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

function fmtVolume(v: number | null | undefined): string {
  if (v == null) return '—'
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(2) + 'M'
  if (v >= 1_000) return (v / 1_000).toFixed(1) + 'K'
  return v.toFixed(0)
}

function calcChangePct(last: number | null, close: number | null): number | null {
  if (last == null || close == null || close === 0) return null
  return ((last - close) / close) * 100
}

// ── symbol autocomplete ───────────────────────────────────────────────────────

interface SymbolSearchProps {
  watchlist: string[]
  onAdd: (symbol: string) => void
}

function SymbolSearch({ watchlist, onAdd }: SymbolSearchProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SymbolSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [])

  // Debounced search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const q = query.trim()
    if (q.length === 0) {
      setResults([])
      setOpen(false)
      setLoading(false)
      return
    }
    setLoading(true)
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await searchSymbols(q)
        setResults(res)
        setOpen(true)
        setActiveIdx(-1)
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }, SEARCH_DEBOUNCE)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [query])

  function select(result: SymbolSearchResult) {
    if (!watchlist.includes(result.symbol)) {
      onAdd(result.symbol)
    }
    setQuery('')
    setOpen(false)
    setResults([])
    inputRef.current?.blur()
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && activeIdx >= 0) {
      e.preventDefault()
      select(results[activeIdx])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const borderRadius = open && (results.length > 0 || (!loading && query.trim().length > 0))
    ? '8px 8px 0 0'
    : '8px'

  return (
    <div ref={containerRef} style={{ position: 'relative', width: 380 }}>
      {/* Input row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          background: 'var(--card)',
          border: '1px solid var(--border)',
          borderRadius,
          padding: '9px 12px',
        }}
      >
        {loading
          ? <Loader size={14} style={{ color: 'var(--muted)', flexShrink: 0, animation: 'spin 0.8s linear infinite' }} />
          : <Search size={14} style={{ color: 'var(--muted)', flexShrink: 0 }} />
        }
        <input
          ref={inputRef}
          value={query}
          onChange={e => setQuery(e.target.value.toUpperCase())}
          onKeyDown={handleKeyDown}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="Search symbol or company..."
          maxLength={20}
          style={{
            background: 'none',
            border: 'none',
            outline: 'none',
            color: 'var(--text)',
            fontSize: 14,
            fontFamily: 'JetBrains Mono, monospace',
            width: '100%',
          }}
        />
        {query && (
          <button
            onClick={() => { setQuery(''); setOpen(false); setResults([]) }}
            style={{
              background: 'none', border: 'none',
              color: 'var(--muted)', cursor: 'pointer',
              padding: 0, lineHeight: 0, flexShrink: 0,
            }}
          >
            <X size={13} />
          </button>
        )}
      </div>

      {/* Dropdown — results */}
      {open && results.length > 0 && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            background: 'var(--card)',
            border: '1px solid var(--border)',
            borderTop: 'none',
            borderRadius: '0 0 8px 8px',
            zIndex: 50,
            maxHeight: 300,
            overflowY: 'auto',
          }}
        >
          {results.map((r, i) => {
            const already = watchlist.includes(r.symbol)
            const isActive = i === activeIdx
            return (
              <button
                key={r.symbol}
                onClick={() => !already && select(r)}
                onMouseEnter={() => setActiveIdx(i)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  width: '100%',
                  background: isActive ? 'rgba(56,139,253,0.1)' : 'transparent',
                  border: 'none',
                  borderBottom: i < results.length - 1 ? '1px solid var(--border)' : 'none',
                  padding: '10px 14px',
                  cursor: already ? 'default' : 'pointer',
                  textAlign: 'left',
                }}
              >
                {/* Symbol */}
                <span
                  className="mono"
                  style={{
                    fontWeight: 600,
                    fontSize: 13,
                    color: already ? 'var(--muted)' : 'var(--text)',
                    minWidth: 56,
                    flexShrink: 0,
                  }}
                >
                  {r.symbol}
                </span>

                {/* Company name */}
                <span
                  style={{
                    fontSize: 12,
                    color: 'var(--muted)',
                    flex: 1,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {r.name || '—'}
                </span>

                {/* Exchange tag */}
                <span
                  style={{
                    fontSize: 10,
                    color: 'var(--muted)',
                    background: 'rgba(139,148,158,0.1)',
                    borderRadius: 4,
                    padding: '2px 6px',
                    flexShrink: 0,
                    fontFamily: 'JetBrains Mono, monospace',
                  }}
                >
                  {r.exchange || r.sec_type}
                </span>

                {already && (
                  <span style={{ fontSize: 10, color: 'var(--muted)', flexShrink: 0 }}>
                    added
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}

      {/* Dropdown — no results */}
      {open && !loading && query.trim().length > 0 && results.length === 0 && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            background: 'var(--card)',
            border: '1px solid var(--border)',
            borderTop: 'none',
            borderRadius: '0 0 8px 8px',
            padding: '12px 14px',
            fontSize: 13,
            color: 'var(--muted)',
            zIndex: 50,
          }}
        >
          No results for "{query}"
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}

// ── ticker card ───────────────────────────────────────────────────────────────

interface TickerState {
  data: MarketDataResponse | null
  error: string | null
  loading: boolean
  flash: 'up' | 'down' | null
}

interface TickerCardProps {
  symbol: string
  onRemove: (symbol: string) => void
}

function TickerCard({ symbol, onRemove }: TickerCardProps) {
  const [state, setState] = useState<TickerState>({
    data: null, error: null, loading: true, flash: null,
  })
  const prevLastRef = useRef<number | null>(null)
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async () => {
    if (retryTimer.current) {
      clearTimeout(retryTimer.current)
      retryTimer.current = null
    }
    try {
      const data = await fetchMarketData(symbol)
      const prevLast = prevLastRef.current
      const newLast = data.last
      let flash: 'up' | 'down' | null = null
      if (prevLast != null && newLast != null && newLast !== prevLast) {
        flash = newLast > prevLast ? 'up' : 'down'
      }
      prevLastRef.current = newLast
      setState({ data, error: null, loading: false, flash })
      if (flash) {
        if (flashTimer.current) clearTimeout(flashTimer.current)
        flashTimer.current = setTimeout(
          () => setState(prev => ({ ...prev, flash: null })),
          600,
        )
      }
      // If subscription just started and tick data isn't ready yet, retry in 2s
      if (newLast == null) {
        retryTimer.current = setTimeout(load, 2000)
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to fetch'
      setState(prev => ({ ...prev, error: msg, loading: false }))
    }
  }, [symbol])

  useEffect(() => {
    load()
    const id = setInterval(load, REFRESH_INTERVAL)
    return () => {
      clearInterval(id)
      if (flashTimer.current) clearTimeout(flashTimer.current)
      if (retryTimer.current) clearTimeout(retryTimer.current)
    }
  }, [load])

  const { data, error, loading, flash } = state
  const changePct = data ? calcChangePct(data.last, data.close) : null
  const isUp = changePct != null && changePct > 0
  const isDown = changePct != null && changePct < 0
  const priceColor = isUp ? 'var(--green)' : isDown ? 'var(--red)' : 'var(--text)'
  const flashBorder =
    flash === 'up' ? 'var(--green)' :
    flash === 'down' ? 'var(--red)' :
    'var(--border)'

  return (
    <div
      style={{
        background: 'var(--card)',
        border: `1px solid ${flashBorder}`,
        borderRadius: 12,
        transition: 'border-color 0.3s ease',
        position: 'relative',
      }}
      className="p-5 flex flex-col gap-4"
    >
      <button
        onClick={() => onRemove(symbol)}
        style={{
          position: 'absolute', top: 10, right: 10,
          background: 'none', border: 'none',
          color: 'var(--muted)', cursor: 'pointer',
          padding: 4, borderRadius: 4, lineHeight: 0,
        }}
        title="Remove"
      >
        <X size={13} />
      </button>

      <span className="mono font-semibold text-base" style={{ color: 'var(--text)' }}>
        {symbol}
      </span>

      <div>
        {loading && !data
          ? <span className="mono text-3xl font-bold" style={{ color: 'var(--muted)' }}>—</span>
          : error
            ? <span className="text-xs" style={{ color: 'var(--red)' }}>{error}</span>
            : (
              <span
                className="mono font-bold"
                style={{ color: priceColor, fontSize: 30, transition: 'color 0.3s ease' }}
              >
                ${fmt(data?.last)}
              </span>
            )
        }
      </div>

      {data && (
        <div className="flex items-center gap-1">
          {isUp && <TrendingUp size={14} style={{ color: 'var(--green)' }} />}
          {isDown && <TrendingDown size={14} style={{ color: 'var(--red)' }} />}
          {!isUp && !isDown && <Minus size={14} style={{ color: 'var(--muted)' }} />}
          <span
            className="mono text-sm font-medium"
            style={{ color: isUp ? 'var(--green)' : isDown ? 'var(--red)' : 'var(--muted)' }}
          >
            {changePct != null ? `${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%` : '—'}
          </span>
          {data.close != null && (
            <span className="text-xs mono" style={{ color: 'var(--muted)', marginLeft: 4 }}>
              vs close ${fmt(data.close)}
            </span>
          )}
        </div>
      )}

      <div
        style={{ borderTop: '1px solid var(--border)', paddingTop: 12 }}
        className="grid grid-cols-3 gap-2"
      >
        {[
          { label: 'BID',    value: data ? `$${fmt(data.bid)}`    : '—' },
          { label: 'ASK',    value: data ? `$${fmt(data.ask)}`    : '—' },
          { label: 'VOLUME', value: data ? fmtVolume(data.volume) : '—' },
        ].map(({ label, value }) => (
          <div key={label} className="flex flex-col gap-1">
            <span style={{ color: 'var(--muted)', fontSize: 10 }}>{label}</span>
            <span className="mono text-xs font-medium" style={{ color: 'var(--text)' }}>{value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function Market() {
  const [symbols, setSymbols] = useState<string[]>(DEFAULT_SYMBOLS)

  function addSymbol(sym: string) {
    setSymbols(prev => prev.includes(sym) ? prev : [...prev, sym])
  }

  function removeSymbol(sym: string) {
    setSymbols(prev => prev.filter(s => s !== sym))
  }

  return (
    <div className="flex flex-col gap-6 max-w-6xl">

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>Market</h1>
          <span className="text-xs mono" style={{ color: 'var(--muted)' }}>
            Live quotes · refreshes every {REFRESH_INTERVAL / 1000}s
          </span>
        </div>
        <div className="flex items-center gap-1" style={{ color: 'var(--muted)' }}>
          <RefreshCw size={12} />
          <span style={{ fontSize: 11 }}>{symbols.length} symbols</span>
        </div>
      </div>

      <SymbolSearch watchlist={symbols} onAdd={addSymbol} />

      {symbols.length === 0 ? (
        <div
          style={{ color: 'var(--muted)', border: '1px dashed var(--border)', borderRadius: 12 }}
          className="flex items-center justify-center py-16 text-sm"
        >
          No symbols — search and add a ticker above
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {symbols.map(sym => (
            <TickerCard key={sym} symbol={sym} onRemove={removeSymbol} />
          ))}
        </div>
      )}
    </div>
  )
}
