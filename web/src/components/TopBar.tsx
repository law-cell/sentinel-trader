import { useEffect, useState } from 'react'
import { Activity } from 'lucide-react'
import axios from 'axios'

type Status = 'checking' | 'api_down' | 'ib_disconnected' | 'connected'

export default function TopBar() {
  const [status, setStatus] = useState<Status>('checking')

  useEffect(() => {
    const check = async () => {
      try {
        const res = await axios.get<{ ib_connected: boolean }>('/api/health')
        setStatus(res.data.ib_connected ? 'connected' : 'ib_disconnected')
      } catch {
        setStatus('api_down')
      }
    }
    check()
    const id = setInterval(check, 5000)
    return () => clearInterval(id)
  }, [])

  const dotColor =
    status === 'connected' ? 'var(--green)' :
    status === 'checking'  ? 'var(--muted)' : 'var(--red)'

  const label =
    status === 'connected'      ? 'IB Connected' :
    status === 'ib_disconnected'? 'IB Disconnected' :
    status === 'api_down'       ? 'API Down' : 'Checking…'

  return (
    <header
      style={{ background: 'var(--card)', borderBottom: '1px solid var(--border)' }}
      className="h-14 flex items-center px-6 gap-3 flex-shrink-0"
    >
      <Activity size={20} style={{ color: 'var(--green)' }} />
      <span className="font-bold text-base tracking-tight" style={{ color: 'var(--text)' }}>
        SentinelTrader
      </span>
      <div className="ml-auto flex items-center gap-2">
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: dotColor,
            boxShadow: status === 'connected' ? '0 0 6px var(--green)' : 'none',
            transition: 'background 0.3s',
          }}
        />
        <span className="text-xs" style={{ color: 'var(--muted)' }}>
          {label}
        </span>
      </div>
    </header>
  )
}
