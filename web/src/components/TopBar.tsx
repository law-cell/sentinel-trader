import { useEffect, useState } from 'react'
import { Activity } from 'lucide-react'
import axios from 'axios'

export default function TopBar() {
  const [connected, setConnected] = useState<boolean | null>(null)

  useEffect(() => {
    const check = async () => {
      try {
        await axios.get('/')
        setConnected(true)
      } catch {
        setConnected(false)
      }
    }
    check()
    const id = setInterval(check, 15000)
    return () => clearInterval(id)
  }, [])

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
            background:
              connected === null ? 'var(--muted)' :
              connected ? 'var(--green)' : 'var(--red)',
            boxShadow: connected ? '0 0 6px var(--green)' : 'none',
            transition: 'background 0.3s',
          }}
        />
        <span className="text-xs" style={{ color: 'var(--muted)' }}>
          {connected === null ? 'Checking…' : connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>
    </header>
  )
}
