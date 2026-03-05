import { useEffect, useState, useCallback } from 'react'
import { Plus, Pencil, Trash2, X, Check, AlertTriangle } from 'lucide-react'
import { fetchRules, createRule, updateRule, deleteRule } from '../api/client'
import type { RuleResponse } from '../types/api'

// ── types ─────────────────────────────────────────────────────────────────────

const CONDITION_TYPES = ['price_above', 'price_below', 'price_change_pct', 'volume_above'] as const
const ACTIONS = ['telegram', 'log', 'console'] as const

type ConditionType = typeof CONDITION_TYPES[number]
type ActionType = typeof ACTIONS[number]

interface FormState {
  name: string
  symbol: string
  condition_type: ConditionType
  threshold: string
  action: ActionType
  cooldown: string
}

const EMPTY_FORM: FormState = {
  name: '',
  symbol: '',
  condition_type: 'price_above',
  threshold: '',
  action: 'telegram',
  cooldown: '300',
}

// ── helpers ───────────────────────────────────────────────────────────────────

function conditionLabel(type: string, threshold: number): string {
  switch (type) {
    case 'price_above':     return `Price > $${threshold}`
    case 'price_below':     return `Price < $${threshold}`
    case 'price_change_pct':return `Change > ${threshold}%`
    case 'volume_above':    return `Vol > ${(threshold / 1_000_000).toFixed(1)}M`
    default:                return `${type} ${threshold}`
  }
}

function relativeTime(iso: string | null): string {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}

// ── shared UI ─────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  background: '#0D1117',
  border: '1px solid var(--border)',
  borderRadius: 8,
  color: 'var(--text)',
  padding: '8px 12px',
  fontSize: 13,
  width: '100%',
  outline: 'none',
}

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--muted)',
  display: 'block',
  marginBottom: 4,
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={labelStyle}>{label.toUpperCase()}</label>
      {children}
    </div>
  )
}

// ── Rule Form Modal ───────────────────────────────────────────────────────────

interface RuleFormProps {
  initial?: RuleResponse | null
  onClose: () => void
  onSaved: () => void
}

function RuleFormModal({ initial, onClose, onSaved }: RuleFormProps) {
  const isEdit = !!initial
  const [form, setForm] = useState<FormState>(() =>
    initial
      ? {
          name: initial.name,
          symbol: initial.symbol,
          condition_type: initial.condition.type as ConditionType,
          threshold: String(initial.condition.threshold),
          action: initial.action as ActionType,
          cooldown: String(initial.cooldown),
        }
      : EMPTY_FORM
  )
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  function set(key: keyof FormState, value: string) {
    setForm(f => ({ ...f, [key]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const threshold = parseFloat(form.threshold)
    const cooldown = parseInt(form.cooldown, 10)
    if (isNaN(threshold) || isNaN(cooldown)) {
      setErr('Threshold and cooldown must be valid numbers.')
      return
    }
    setSaving(true)
    setErr(null)
    try {
      const payload = {
        name: form.name.trim(),
        symbol: form.symbol.trim().toUpperCase(),
        condition: { type: form.condition_type, threshold },
        action: form.action,
        cooldown,
        enabled: true,
      }
      if (isEdit) {
        await updateRule(initial!.name, {
          condition: payload.condition,
          action: payload.action,
          cooldown: payload.cooldown,
        })
      } else {
        await createRule(payload)
      }
      onSaved()
      onClose()
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErr(detail ?? (e instanceof Error ? e.message : 'Request failed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 14, width: '100%', maxWidth: 480, padding: 28 }}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="font-semibold text-base" style={{ color: 'var(--text)' }}>
            {isEdit ? 'Edit Rule' : 'New Rule'}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)' }}>
            <X size={18} />
          </button>
        </div>

        {err && (
          <div style={{ background: 'rgba(255,68,68,0.1)', border: '1px solid var(--red)', borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 13, color: 'var(--red)' }}>
            {err}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Field label="Rule Name">
            <input
              style={inputStyle}
              value={form.name}
              onChange={e => set('name', e.target.value)}
              placeholder="NVDA Price Alert"
              required
              disabled={isEdit}
            />
          </Field>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Field label="Symbol">
              <input
                style={{ ...inputStyle, textTransform: 'uppercase' }}
                value={form.symbol}
                onChange={e => set('symbol', e.target.value)}
                placeholder="NVDA"
                required
                disabled={isEdit}
              />
            </Field>
            <Field label="Action">
              <select
                style={{ ...inputStyle, cursor: 'pointer' }}
                value={form.action}
                onChange={e => set('action', e.target.value as ActionType)}
              >
                {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
            </Field>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Field label="Condition Type">
              <select
                style={{ ...inputStyle, cursor: 'pointer' }}
                value={form.condition_type}
                onChange={e => set('condition_type', e.target.value as ConditionType)}
              >
                {CONDITION_TYPES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Threshold">
              <input
                style={inputStyle}
                type="number"
                step="any"
                value={form.threshold}
                onChange={e => set('threshold', e.target.value)}
                placeholder="150"
                required
              />
            </Field>
          </div>

          <Field label="Cooldown (seconds)">
            <input
              style={inputStyle}
              type="number"
              min="0"
              value={form.cooldown}
              onChange={e => set('cooldown', e.target.value)}
              required
            />
          </Field>

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 4 }}>
            <button
              type="button"
              onClick={onClose}
              style={{ background: 'transparent', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--muted)', padding: '8px 18px', fontSize: 13, cursor: 'pointer' }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              style={{
                background: 'var(--green)',
                border: 'none',
                borderRadius: 8,
                color: '#000',
                fontWeight: 600,
                padding: '8px 20px',
                fontSize: 13,
                cursor: saving ? 'not-allowed' : 'pointer',
                opacity: saving ? 0.7 : 1,
              }}
            >
              {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Rule'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Delete Confirm Modal ──────────────────────────────────────────────────────

function DeleteModal({ ruleName, onClose, onDeleted }: { ruleName: string; onClose: () => void; onDeleted: () => void }) {
  const [deleting, setDeleting] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function handleDelete() {
    setDeleting(true)
    try {
      await deleteRule(ruleName)
      onDeleted()
      onClose()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Delete failed')
      setDeleting(false)
    }
  }

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 14, width: '100%', maxWidth: 400, padding: 28 }}>
        <div className="flex items-center gap-3 mb-4">
          <AlertTriangle size={20} style={{ color: 'var(--red)', flexShrink: 0 }} />
          <h2 className="font-semibold text-base" style={{ color: 'var(--text)' }}>Delete Rule</h2>
        </div>
        <p style={{ color: 'var(--muted)', fontSize: 14, marginBottom: 6 }}>
          Are you sure you want to delete:
        </p>
        <p className="mono" style={{ color: 'var(--text)', fontSize: 14, marginBottom: 20, wordBreak: 'break-word' }}>
          "{ruleName}"
        </p>
        {err && (
          <p style={{ color: 'var(--red)', fontSize: 13, marginBottom: 12 }}>{err}</p>
        )}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--muted)', padding: '8px 18px', fontSize: 13, cursor: 'pointer' }}
          >
            Cancel
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            style={{ background: 'var(--red)', border: 'none', borderRadius: 8, color: '#fff', fontWeight: 600, padding: '8px 20px', fontSize: 13, cursor: deleting ? 'not-allowed' : 'pointer', opacity: deleting ? 0.7 : 1 }}
          >
            {deleting ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Toggle Switch ─────────────────────────────────────────────────────────────

function Toggle({ enabled, onChange }: { enabled: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!enabled)}
      style={{
        width: 38,
        height: 22,
        borderRadius: 11,
        background: enabled ? 'var(--green)' : 'var(--border)',
        border: 'none',
        cursor: 'pointer',
        position: 'relative',
        transition: 'background 0.2s',
        flexShrink: 0,
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: 3,
          left: enabled ? 19 : 3,
          width: 16,
          height: 16,
          borderRadius: '50%',
          background: '#fff',
          transition: 'left 0.2s',
        }}
      />
    </button>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Rules() {
  const [rules, setRules] = useState<RuleResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editTarget, setEditTarget] = useState<RuleResponse | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await fetchRules()
      setRules(data)
      setError(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load rules')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleToggle(rule: RuleResponse) {
    try {
      await updateRule(rule.name, { enabled: !rule.enabled })
      setRules(rs => rs.map(r => r.name === rule.name ? { ...r, enabled: !r.enabled } : r))
    } catch {
      // silently ignore
    }
  }

  const COLS = ['Name', 'Symbol', 'Condition', 'Action', 'Cooldown', 'Status', 'Last Triggered', '']

  return (
    <div className="flex flex-col gap-6 max-w-6xl">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>Rules</h1>
          <span className="text-xs mono" style={{ color: 'var(--muted)' }}>{rules.length} rules</span>
        </div>
        <button
          onClick={() => { setEditTarget(null); setShowForm(true) }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            background: 'var(--green)',
            border: 'none',
            borderRadius: 8,
            color: '#000',
            fontWeight: 600,
            padding: '8px 16px',
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          <Plus size={15} />
          New Rule
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{ background: 'rgba(255,68,68,0.1)', border: '1px solid var(--red)', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: 'var(--red)' }}>
          {error}
        </div>
      )}

      {/* Table */}
      <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
        {loading ? (
          <div className="flex items-center justify-center py-16" style={{ color: 'var(--muted)', fontSize: 14 }}>
            Loading rules…
          </div>
        ) : rules.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3" style={{ color: 'var(--muted)' }}>
            <p className="text-sm">No rules configured.</p>
            <button
              onClick={() => { setEditTarget(null); setShowForm(true) }}
              style={{ color: 'var(--green)', background: 'none', border: 'none', fontSize: 13, cursor: 'pointer', textDecoration: 'underline' }}
            >
              Create your first rule
            </button>
          </div>
        ) : (
          <table className="w-full text-sm" style={{ borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {COLS.map(h => (
                  <th key={h} className="px-5 py-3 text-left font-medium" style={{ color: 'var(--muted)', fontSize: 11, whiteSpace: 'nowrap' }}>
                    {h.toUpperCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr
                  key={rule.name}
                  style={{ borderBottom: '1px solid var(--border)' }}
                  className="hover:bg-white/5 transition-colors"
                >
                  {/* Name */}
                  <td className="px-5 py-3" style={{ color: 'var(--text)', maxWidth: 200 }}>
                    <span className="block truncate font-medium" title={rule.name}>{rule.name}</span>
                  </td>

                  {/* Symbol */}
                  <td className="px-5 py-3">
                    <span className="mono font-semibold" style={{ color: 'var(--green)' }}>{rule.symbol}</span>
                  </td>

                  {/* Condition */}
                  <td className="px-5 py-3 mono" style={{ color: 'var(--text)', whiteSpace: 'nowrap' }}>
                    {conditionLabel(rule.condition.type, rule.condition.threshold)}
                  </td>

                  {/* Action */}
                  <td className="px-5 py-3" style={{ color: 'var(--muted)' }}>{rule.action}</td>

                  {/* Cooldown */}
                  <td className="px-5 py-3 mono" style={{ color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                    {rule.cooldown}s
                  </td>

                  {/* Status toggle */}
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <Toggle enabled={rule.enabled} onChange={() => handleToggle(rule)} />
                      <span style={{ fontSize: 12, color: rule.enabled ? 'var(--green)' : 'var(--muted)' }}>
                        {rule.enabled ? 'On' : 'Off'}
                      </span>
                    </div>
                  </td>

                  {/* Last triggered */}
                  <td className="px-5 py-3 mono" style={{ color: 'var(--muted)', fontSize: 12, whiteSpace: 'nowrap' }}>
                    {relativeTime(rule.last_triggered)}
                  </td>

                  {/* Actions */}
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => { setEditTarget(rule); setShowForm(true) }}
                        title="Edit"
                        style={{ background: 'rgba(56,139,253,0.1)', border: '1px solid rgba(56,139,253,0.3)', borderRadius: 6, color: 'var(--accent)', padding: '5px 10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}
                      >
                        <Pencil size={13} /> Edit
                      </button>
                      <button
                        onClick={() => setDeleteTarget(rule.name)}
                        title="Delete"
                        style={{ background: 'rgba(255,68,68,0.1)', border: '1px solid rgba(255,68,68,0.3)', borderRadius: 6, color: 'var(--red)', padding: '5px 10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}
                      >
                        <Trash2 size={13} /> Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-6" style={{ fontSize: 12, color: 'var(--muted)' }}>
        <span className="flex items-center gap-1"><Check size={12} style={{ color: 'var(--green)' }} /> Active rule fires alerts</span>
        <span>Cooldown prevents duplicate alerts within the set period</span>
      </div>

      {/* Modals */}
      {showForm && (
        <RuleFormModal
          initial={editTarget}
          onClose={() => { setShowForm(false); setEditTarget(null) }}
          onSaved={load}
        />
      )}
      {deleteTarget && (
        <DeleteModal
          ruleName={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onDeleted={load}
        />
      )}
    </div>
  )
}
