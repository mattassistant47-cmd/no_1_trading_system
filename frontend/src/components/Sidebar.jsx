import { Link, useLocation } from 'react-router-dom'
import {
  BarChart3, Boxes, TrendingUp, Zap, AlertTriangle, Settings,
  ChevronRight
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { path: '/', icon: BarChart3, label: 'Dashboard' },
  { path: '/positions', icon: Boxes, label: 'Positions' },
  { path: '/trades', icon: TrendingUp, label: 'Trades' },
  { path: '/strategies', icon: Zap, label: 'Strategies' },
  { path: '/risk', icon: AlertTriangle, label: 'Risk' },
  { path: '/system', icon: Settings, label: 'System' },
]

export default function Sidebar() {
  const location = useLocation()

  return (
    <aside className="w-64 bg-card-bg border-r border-surface flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-surface">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-8 h-8 bg-neon-green rounded flex items-center justify-center">
            <span className="text-dark-bg font-bold text-sm">⬤</span>
          </div>
          <span className="text-neon-green font-bold text-lg tracking-wider">
            N1 TRADING
          </span>
        </div>
        <div className="text-xs text-muted">Autonomous Multi-Asset System</div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-2">
        {navItems.map(({ path, icon: Icon, label }) => {
          const isActive = location.pathname === path
          return (
            <Link
              key={path}
              to={path}
              className={clsx(
                'flex items-center gap-3 px-4 py-3 rounded transition-all duration-200',
                'hover:bg-surface hover:text-neon-green',
                isActive && 'bg-surface text-neon-green border-l-2 border-neon-green'
              )}
            >
              <Icon className="w-5 h-5" />
              <span className="flex-1">{label}</span>
              {isActive && <ChevronRight className="w-4 h-4" />}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-surface text-xs text-muted space-y-1">
        <div>System: <span className="text-neon-green">LIVE</span></div>
        <div>Mode: <span className="text-neon-cyan">Paper</span></div>
      </div>
    </aside>
  )
}
