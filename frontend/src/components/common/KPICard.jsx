import { ArrowUpRight, ArrowDownRight, TrendingUp, DollarSign, PercentSquare, Activity } from 'lucide-react'
import clsx from 'clsx'

const iconMap = {
  TrendingUp,
  DollarSign,
  PercentSquare,
  Activity,
}

export default function KPICard({ label, value, change, changeLabel = 'today', positive, icon = 'TrendingUp' }) {
  const Icon = iconMap[icon] || TrendingUp

  return (
    <div className="bg-card-bg rounded border border-surface p-6 hover:border-neon-cyan transition">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="text-xs text-muted uppercase tracking-wider mb-1">{label}</div>
          <div className="text-2xl font-bold text-bright">{value}</div>
        </div>
        <Icon className={clsx(
          'w-6 h-6',
          positive ? 'text-neon-green' : 'text-neon-red'
        )} />
      </div>

      {typeof change === 'number' && (
        <div className="flex items-center gap-1">
          {positive ? (
            <ArrowUpRight className="w-4 h-4 text-neon-green" />
          ) : (
            <ArrowDownRight className="w-4 h-4 text-neon-red" />
          )}
          <span className={clsx(
            'text-sm font-semibold',
            positive ? 'text-neon-green' : 'text-neon-red'
          )}>
            {positive ? '+' : ''}{change.toFixed(2)}%
          </span>
          <span className="text-xs text-muted">{changeLabel}</span>
        </div>
      )}
    </div>
  )
}
