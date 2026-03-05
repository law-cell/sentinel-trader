import { NavLink } from 'react-router-dom'
import { LayoutDashboard, ScrollText, BarChart2, Settings } from 'lucide-react'

const NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/rules', icon: ScrollText, label: 'Rules' },
  { to: '/market', icon: BarChart2, label: 'Market' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
  return (
    <aside
      style={{ background: 'var(--card)', borderRight: '1px solid var(--border)' }}
      className="w-56 flex-shrink-0 flex flex-col py-6 gap-1"
    >
      {NAV.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          style={({ isActive }) => ({
            color: isActive ? 'var(--green)' : 'var(--muted)',
            background: isActive ? 'rgba(0,214,50,0.08)' : 'transparent',
            borderLeft: isActive ? '2px solid var(--green)' : '2px solid transparent',
          })}
          className="flex items-center gap-3 px-5 py-2.5 text-sm font-medium transition-colors hover:text-white"
        >
          <Icon size={18} />
          {label}
        </NavLink>
      ))}
    </aside>
  )
}
