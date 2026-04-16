import { useEffect, useState, useContext } from 'react'
import { useApi } from '../hooks/useApi'
import { AppContext } from '../App'
import KPICard from './common/KPICard'
import DataTable from './common/DataTable'
import StatusBadge from './common/StatusBadge'
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import { ArrowUpRight, ArrowDownRight } from 'lucide-react'
import clsx from 'clsx'

const snakeToCamel = (obj) => {
  if (obj === null || obj === undefined || typeof obj !== 'object') return obj;
  if (Array.isArray(obj)) return obj.map(snakeToCamel);
  return Object.fromEntries(
    Object.entries(obj).map(([k, v]) => [
      k.replace(/_([a-z])/g, (_, c) => c.toUpperCase()),
      snakeToCamel(v)
    ])
  );
};

export default function Dashboard() {
  const { wsConnected, realtimeData } = useContext(AppContext)
  const [dashboardData, setDashboardData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const { get } = useApi()

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        const data = await get('/api/dashboard/overview')
        setDashboardData(snakeToCamel(data))
        setError(null)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [get])

  if (loading && !dashboardData) {
    return (
      <div className="p-8 space-y-8 animate-pulse">
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-32 bg-card-bg rounded" />
          ))}
        </div>
      </div>
    )
  }

  if (error && !dashboardData) {
    return (
      <div className="p-8 bg-neon-red/10 border border-neon-red rounded text-neon-red">
        Error loading dashboard: {error}
      </div>
    )
  }

  if (!dashboardData) {
    return (
      <div className="p-8 text-center text-muted">No trading data yet</div>
    )
  }

  const {
    portfolioValue = 100000,
    dailyPnL = 1250,
    totalReturn = 12.5,
    sharpeRatio = 1.8,
    equityCurve = [],
    assetAllocation = [],
    recentTrades = [],
    activeSignals = [],
    strategyPerformance = [],
  } = dashboardData || {}

  const dailyPnLPercent = portfolioValue ? (dailyPnL / portfolioValue) * 100 : 0
  const isProfitable = dailyPnL >= 0

  return (
    <div className="p-8 space-y-8">
      {/* Status Bar */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <div className="flex items-center gap-3">
          <div className={clsx('flex items-center gap-2 px-3 py-1 rounded text-sm', wsConnected ? 'bg-neon-green/20 text-neon-green' : 'bg-neon-red/20 text-neon-red')}>
            <div className={clsx('w-2 h-2 rounded-full', wsConnected ? 'bg-neon-green animate-pulse' : 'bg-neon-red')} />
            {wsConnected ? 'Real-time' : 'Disconnected'}
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          label="Portfolio Value"
          value={`$${(portfolioValue || 0).toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
          change={dailyPnLPercent}
          positive={isProfitable}
          icon="TrendingUp"
        />
        <KPICard
          label="Daily P&L"
          value={`$${(dailyPnL || 0).toLocaleString('en-US', { maximumFractionDigits: 2 })}`}
          change={dailyPnLPercent}
          positive={isProfitable}
          icon="DollarSign"
        />
        <KPICard
          label="Total Return"
          value={`${(totalReturn || 0).toFixed(2)}%`}
          change={totalReturn}
          positive={totalReturn >= 0}
          icon="PercentSquare"
        />
        <KPICard
          label="Sharpe Ratio"
          value={(sharpeRatio || 0).toFixed(2)}
          change={sharpeRatio}
          positive={sharpeRatio >= 1}
          icon="Activity"
        />
      </div>

      {/* Charts Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Equity Curve */}
        <div className="lg:col-span-2 bg-card-bg rounded border border-surface p-6">
          <h3 className="text-lg font-semibold mb-4 text-neon-cyan">Equity Curve</h3>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={equityCurve}>
              <defs>
                <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00ff88" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#00ff88" stopOpacity={0.1} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="date" stroke="#94a3b8" style={{ fontSize: '12px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '12px' }} />
              <Tooltip
                contentStyle={{ backgroundColor: '#111827', border: '1px solid #1e293b' }}
                labelStyle={{ color: '#00ff88' }}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="#00ff88"
                fill="url(#colorPnl)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Asset Allocation */}
        <div className="bg-card-bg rounded border border-surface p-6">
          <h3 className="text-lg font-semibold mb-4 text-neon-cyan">Asset Allocation</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={assetAllocation}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {assetAllocation.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={['#00ff88', '#00e5ff', '#ff3366'][index % 3]}
                  />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ backgroundColor: '#111827', border: '1px solid #1e293b' }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Charts Row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Strategy Performance */}
        <div className="bg-card-bg rounded border border-surface p-6">
          <h3 className="text-lg font-semibold mb-4 text-neon-cyan">Strategy Performance</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={strategyPerformance}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="name" stroke="#94a3b8" style={{ fontSize: '12px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '12px' }} />
              <Tooltip
                contentStyle={{ backgroundColor: '#111827', border: '1px solid #1e293b' }}
              />
              <Bar dataKey="return" fill="#00ff88" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Active Signals */}
        <div className="bg-card-bg rounded border border-surface p-6">
          <h3 className="text-lg font-semibold mb-4 text-neon-cyan">Active Signals</h3>
          <div className="space-y-3">
            {activeSignals.length > 0 ? (
              activeSignals.slice(0, 5).map((signal, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-surface rounded border border-grid">
                  <div>
                    <div className="font-semibold text-bright">{signal?.symbol}</div>
                    <div className="text-xs text-muted">{signal?.strategy}</div>
                  </div>
                  <StatusBadge
                    status={signal.type === 'BUY' ? 'success' : 'warning'}
                    label={signal.type}
                  />
                </div>
              ))
            ) : (
              <div className="text-center text-muted py-4">No active signals</div>
            )}
          </div>
        </div>
      </div>

      {/* Recent Trades Table */}
      <div className="bg-card-bg rounded border border-surface p-6">
        <h3 className="text-lg font-semibold mb-4 text-neon-cyan">Recent Trades</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-grid">
              <tr className="text-muted">
                <th className="text-left py-3 px-2">Symbol</th>
                <th className="text-left py-3 px-2">Side</th>
                <th className="text-right py-3 px-2">Qty</th>
                <th className="text-right py-3 px-2">Entry</th>
                <th className="text-right py-3 px-2">Exit</th>
                <th className="text-right py-3 px-2">P&L</th>
                <th className="text-left py-3 px-2">Strategy</th>
                <th className="text-left py-3 px-2">Date</th>
              </tr>
            </thead>
            <tbody>
              {recentTrades.length > 0 ? (
                recentTrades.map((trade, i) => (
                  <tr
                    key={i}
                    className="border-b border-grid hover:bg-surface/50 transition"
                  >
                    <td className="py-3 px-2 font-semibold">{trade?.symbol}</td>
                    <td className="py-3 px-2">
                      <span className={clsx(
                        'px-2 py-1 rounded text-xs font-semibold',
                        trade?.side === 'BUY'
                          ? 'bg-neon-green/20 text-neon-green'
                          : 'bg-neon-red/20 text-neon-red'
                      )}>
                        {trade?.side}
                      </span>
                    </td>
                    <td className="py-3 px-2 text-right">{trade?.qty}</td>
                    <td className="py-3 px-2 text-right">${(trade?.entryPrice || 0).toFixed(2)}</td>
                    <td className="py-3 px-2 text-right">${(trade?.exitPrice || 0).toFixed(2)}</td>
                    <td className={clsx(
                      'py-3 px-2 text-right font-semibold',
                      (trade?.pnl || 0) >= 0 ? 'text-neon-green' : 'text-neon-red'
                    )}>
                      ${(trade?.pnl || 0).toFixed(2)}
                    </td>
                    <td className="py-3 px-2 text-muted text-xs">{trade?.strategy}</td>
                    <td className="py-3 px-2 text-muted text-xs">{trade?.date}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="8" className="text-center py-4 text-muted">
                    No trades yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
