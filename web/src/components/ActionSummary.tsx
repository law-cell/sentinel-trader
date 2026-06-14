import type { Action } from '../types/api'

// ── Compact summary (used in the rules table) ──────────────────────────────────

export function actionShortLabel(action: Action, channel: string): string {
  switch (action.type) {
    case 'alert':
      return `Alert via ${channel}`
    case 'propose_stock_order':
      return `Propose ${action.side} ${action.quantity} sh (${action.order_type})`
    case 'propose_option_order':
      return `Propose SELL ${action.quantity}x ${action.right} $${action.strike} (${action.expiry_days}d)`
  }
}

// ── Detailed summary (used in the "Create with AI" preview) ────────────────────

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', gap: 10 }}>
      <span style={{ color: 'var(--muted)', minWidth: 90 }}>{label}:</span>
      <span style={{ color: 'var(--text)' }}>{value}</span>
    </div>
  )
}

function SubList({ items }: { items: string[] }) {
  return (
    <div style={{ paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 2, fontSize: 12, color: 'var(--muted)' }}>
      {items.map(item => <div key={item}>• {item}</div>)}
    </div>
  )
}

export function ActionDetail({ action, channel }: { action: Action; channel: string }) {
  switch (action.type) {
    case 'alert':
      return <Row label="Action" value={`Send alert via ${channel}`} />

    case 'propose_stock_order': {
      const items = [
        `Side: ${action.side}`,
        `Quantity: ${action.quantity} share${action.quantity !== 1 ? 's' : ''}`,
        `Order type: ${action.order_type}`,
      ]
      if (action.order_type === 'LIMIT' && action.limit_price != null) {
        items.push(`Limit price: $${action.limit_price.toFixed(2)}`)
      }
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <Row label="Action" value="Propose stock order on trigger" />
          <SubList items={items} />
        </div>
      )
    }

    case 'propose_option_order':
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <Row label="Action" value="Propose option order on trigger" />
          <SubList items={[
            `Right: ${action.right === 'C' ? 'Call (C)' : 'Put (P)'}`,
            `Strike: $${action.strike.toFixed(2)}`,
            `Expiry: ${action.expiry_days} days from rule trigger`,
            `Quantity: ${action.quantity} contract${action.quantity !== 1 ? 's' : ''}`,
            'Side: SELL (sell-to-open, forced by policy)',
          ]} />
        </div>
      )
  }
}
