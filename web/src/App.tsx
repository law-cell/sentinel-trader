import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Rules from './pages/Rules'
import Market from './pages/Market'

function Placeholder({ name }: { name: string }) {
  return (
    <div className="flex items-center justify-center h-64">
      <span style={{ color: 'var(--muted)' }}>{name} — coming soon</span>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="/rules" element={<Rules />} />
          <Route path="/market" element={<Market />} />
          <Route path="/settings" element={<Placeholder name="Settings" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
