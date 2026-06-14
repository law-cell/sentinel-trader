import { useState } from 'react'
import { ChevronDown, ChevronUp, Loader2, Check, AlertTriangle, Info } from 'lucide-react'
import { extractRuleFromNL, createRule } from '../api/client'
import type { RuleResponse, RuleCondition } from '../types/api'
import { ActionDetail } from './ActionSummary'

const EXAMPLES = [
  'Alert me when NVDA crosses above $200',
  'Buy 10 TSLA when it drops below $250',
  'Sell a covered call on NVDA at 240 strike, 30 days, when NVDA hits $220',
]

type Phase = 'idle' | 'loading' | 'extracted' | 'validation_error' | 'clarification_needed' | 'saved'

function triggerDescription(condition: RuleCondition): string {
  switch (condition.type) {
    case 'price_above':
      return `Price above $${condition.threshold.toFixed(2)}`
    case 'price_below':
      return `Price below $${condition.threshold.toFixed(2)}`
    case 'price_change_pct': {
      const sign = condition.threshold > 0 ? '+' : ''
      return `Price changes ${sign}${condition.threshold}% from previous close`
    }
    case 'volume_above':
      return `Volume above ${condition.threshold.toLocaleString()}`
    default:
      return `${condition.type} ${condition.threshold}`
  }
}

function formatCooldown(seconds: number): string {
  if (seconds % 3600 === 0) {
    const h = seconds / 3600
    return `${h} hour${h !== 1 ? 's' : ''} between triggers`
  }
  if (seconds % 60 === 0) {
    const m = seconds / 60
    return `${m} minute${m !== 1 ? 's' : ''} between triggers`
  }
  return `${seconds}s between triggers`
}

function Row({ label, value, mono, accent }: { label: string; value: string; mono?: boolean; accent?: boolean }) {
  return (
    <div style={{ display: 'flex', gap: 10 }}>
      <span style={{ color: 'var(--muted)', minWidth: 90 }}>{label}:</span>
      <span className={mono ? 'mono' : undefined} style={{ color: accent ? 'var(--green)' : 'var(--text)', fontWeight: accent ? 600 : 400 }}>
        {value}
      </span>
    </div>
  )
}

// ── shared styles ────────────────────────────────────────────────────────────

const textareaStyle: React.CSSProperties = {
  background: '#0D1117',
  border: '1px solid var(--border)',
  borderRadius: 8,
  color: 'var(--text)',
  padding: '10px 12px',
  fontSize: 13,
  width: '100%',
  outline: 'none',
  resize: 'vertical',
  fontFamily: 'inherit',
}

const cancelBtnStyle: React.CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--border)',
  borderRadius: 8,
  color: 'var(--muted)',
  padding: '8px 18px',
  fontSize: 13,
  cursor: 'pointer',
}

function primaryBtnStyle(disabled: boolean): React.CSSProperties {
  return {
    background: 'var(--green)',
    border: 'none',
    borderRadius: 8,
    color: '#000',
    fontWeight: 600,
    padding: '8px 20px',
    fontSize: 13,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.7 : 1,
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  }
}

// ── Main component ──────────────────────────────────────────────────────────

export default function CreateRuleWithAI({ onSaved }: { onSaved: () => void }) {
  const [expanded, setExpanded] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [extractedRule, setExtractedRule] = useState<RuleResponse | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const [clarification, setClarification] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function reset() {
    setPrompt('')
    setPhase('idle')
    setExtractedRule(null)
    setErrors([])
    setClarification('')
    setError(null)
  }

  function handleCancel() {
    setExpanded(false)
    reset()
  }

  async function handleTest() {
    if (!prompt.trim()) return
    setPhase('loading')
    setError(null)
    try {
      const result = await extractRuleFromNL(prompt.trim(), true)
      if (result.status === 'ok') {
        setExtractedRule(result.rule)
        setPhase('extracted')
      } else {
        setExtractedRule(result.rule)
        setErrors(result.errors)
        setPhase('validation_error')
      }
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      if (detail) {
        setClarification(detail)
        setPhase('clarification_needed')
      } else {
        setError(e instanceof Error ? e.message : 'Request failed')
        setPhase('idle')
      }
    }
  }

  async function handleSave() {
    if (!extractedRule) return
    setSaving(true)
    setError(null)
    try {
      await createRule({
        name: extractedRule.name,
        symbol: extractedRule.symbol,
        condition: extractedRule.condition,
        channel: extractedRule.channel,
        action: extractedRule.action,
        cooldown: extractedRule.cooldown,
        enabled: extractedRule.enabled,
      })
      setPhase('saved')
      onSaved()
      setTimeout(() => {
        setExpanded(false)
        reset()
      }, 2000)
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? (e instanceof Error ? e.message : 'Save failed'))
    } finally {
      setSaving(false)
    }
  }

  function handleEditPrompt() {
    setPhase('idle')
    setExtractedRule(null)
    setErrors([])
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      handleTest()
    }
  }

  const showPromptInput =
    phase === 'idle' || phase === 'loading' || phase === 'validation_error' || phase === 'clarification_needed'

  return (
    <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
      {/* Header */}
      <button
        onClick={() => (expanded ? handleCancel() : setExpanded(true))}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: '14px 20px',
          color: 'var(--text)',
          fontSize: 14,
          fontWeight: 600,
        }}
      >
        <span>
          ✨ Create with AI{' '}
          <span style={{ color: 'var(--muted)', fontWeight: 400, fontSize: 12 }}>· powered by Claude</span>
        </span>
        {expanded ? <ChevronUp size={16} style={{ color: 'var(--muted)' }} /> : <ChevronDown size={16} style={{ color: 'var(--muted)' }} />}
      </button>

      {expanded && (
        <div style={{ padding: '0 20px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>

          {error && (
            <div style={{ background: 'rgba(255,68,68,0.1)', border: '1px solid var(--red)', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: 'var(--red)' }}>
              {error}
            </div>
          )}

          {showPromptInput && (
            <>
              <div>
                <label style={{ fontSize: 12, color: 'var(--muted)', display: 'block', marginBottom: 6 }}>
                  Describe what you want to monitor or trade:
                </label>
                <textarea
                  value={prompt}
                  onChange={e => setPrompt(e.target.value.slice(0, 500))}
                  onKeyDown={handleKeyDown}
                  disabled={phase === 'loading'}
                  rows={4}
                  maxLength={500}
                  placeholder="e.g. Alert me when NVDA crosses above $200"
                  style={textareaStyle}
                />
              </div>

              {phase === 'validation_error' && (
                <div style={{ background: 'rgba(255,170,0,0.08)', border: '1px solid #FFAA00', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: '#FFAA00', display: 'flex', gap: 8 }}>
                  <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                  <div>
                    <div style={{ marginBottom: 4, fontWeight: 600 }}>This rule doesn't meet the safety policy:</div>
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {errors.map(e => <li key={e}>{e}</li>)}
                    </ul>
                  </div>
                </div>
              )}

              {phase === 'clarification_needed' && (
                <div style={{ background: 'rgba(56,139,253,0.08)', border: '1px solid var(--accent)', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: 'var(--text)', display: 'flex', gap: 8 }}>
                  <Info size={16} style={{ flexShrink: 0, marginTop: 1, color: 'var(--accent)' }} />
                  <div style={{ whiteSpace: 'pre-wrap' }}>{clarification}</div>
                </div>
              )}

              {phase === 'idle' && (
                <div style={{ fontSize: 12, color: 'var(--muted)' }}>
                  <div style={{ marginBottom: 6 }}>Examples:</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {EXAMPLES.map(ex => (
                      <button
                        key={ex}
                        onClick={() => setPrompt(ex)}
                        style={{ background: 'none', border: 'none', color: 'var(--accent)', fontSize: 12, textAlign: 'left', cursor: 'pointer', padding: 0 }}
                      >
                        • "{ex}"
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                <button onClick={handleCancel} style={cancelBtnStyle}>Cancel</button>
                <button onClick={handleTest} disabled={phase === 'loading' || !prompt.trim()} style={primaryBtnStyle(phase === 'loading' || !prompt.trim())}>
                  {phase === 'loading' ? (
                    <>
                      <Loader2 size={14} className="animate-spin" /> Claude is thinking…
                    </>
                  ) : 'Test interpretation'}
                </button>
              </div>
            </>
          )}

          {phase === 'extracted' && extractedRule && (
            <>
              <div style={{ background: '#0D1117', border: '1px solid var(--border)', borderRadius: 8, padding: 16, fontSize: 13 }}>
                <div style={{ color: 'var(--muted)', fontSize: 11, marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                  Claude understood
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <Row label="Rule name" value={extractedRule.name} />
                  <Row label="Symbol" value={extractedRule.symbol} mono accent />
                  <Row label="Trigger" value={triggerDescription(extractedRule.condition)} />
                  <div style={{ borderTop: '1px solid var(--border)', margin: '6px 0' }} />
                  <ActionDetail action={extractedRule.action} channel={extractedRule.channel} />
                  <div style={{ borderTop: '1px solid var(--border)', margin: '6px 0' }} />
                  <Row label="Cooldown" value={formatCooldown(extractedRule.cooldown)} />
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>Looks right?</span>
                <div style={{ display: 'flex', gap: 10 }}>
                  <button onClick={handleCancel} style={cancelBtnStyle}>Cancel</button>
                  <button onClick={handleEditPrompt} style={cancelBtnStyle}>Edit prompt</button>
                  <button onClick={handleSave} disabled={saving} style={primaryBtnStyle(saving)}>
                    {saving ? (
                      <>
                        <Loader2 size={14} className="animate-spin" /> Saving…
                      </>
                    ) : 'Save rule'}
                  </button>
                </div>
              </div>
            </>
          )}

          {phase === 'saved' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--green)', fontSize: 13, padding: '8px 0' }}>
              <Check size={16} /> Rule created
            </div>
          )}
        </div>
      )}
    </div>
  )
}
