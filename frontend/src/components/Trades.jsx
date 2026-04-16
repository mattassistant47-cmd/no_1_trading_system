import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import clsx from 'clsx'
import { Calendar } from 'lucide-react'

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

export default function Trades() {
  const [trades, setTrades] = useState([])
  const [stats, setStats] = useState(null)
  const [pnlChart, setPnlChart] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [sortConfig, setSortConfig] = useState({ key: 'date', direction: 'desc' })

  const { get } = useApi()

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        const params = new URLSearchParams()
        if (startDate) params.append('startDate', startDate)
        if (endDate) params.append('endDate', endDate)

        const tradesData = await get(`/api/trades?${params}`)
        let statsData = null
        let pnlData = []
        try { statsData = await get(`/api/trades/stats?${params}`) } catch (e) { /* optional */ }
        try { pnlData = await get(`/api/trades/pnl-distribution?${params}`) } catch (e) { /* optional */ }

        setTrades(snakeToCamel(Array.isArray(tradesData) ? tradesData : []))
        setStats(snakeToCamel(statsData))
        setPnlChart(snakeToCamel(Array.isArray(pnlData) ? pnlData : []))
        setError(null)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [get, startDate, endDate])

  const handleSort = (key) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }))
  }

  let sorted = [...trades]
  if (sortConfig.key) {
    sorted.sort((a, b) => {
      const aVal = a[sortConfig.key]
      const bVal = b[sortConfig.key]
      const comparison = aVal > bVal ? 1 : -1
      return sortConfig.direction === 'asc' ? comparison : -comparison
    })
  }

  const filtered = sorted.filter(t =>
    (t?.symbol || '').toLowerCase().includes(filter.toLowerCase()) ||
    (t?.strategy || '').toLowerCase().includes(filter.toLowerCase())
  )

  if (error) {
    return (
      <div className="p-8 bg-neon-red/10 border border-neon-red rounded text-neon-red">
        Error loading trades: {error}
      </div>
    )
  }

  return (
    <div className="p-8 space-y-8">
      <h1 className="text-3xl font-bold">Trade History</h1>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <div className="bg-card-bg rounded border border-surface p-4">
            <div className="text-xs text-muted mb-1">Win Rate</div>
            <div className="text-2xl font-bold text-neon-cyan">{stats.winRate?.toFixed(1)}%</div>
          </div>
          <div className="bg-card-bg rounded border border-surface p-4">
            <div className="text-xs text-muted mb-1">Avg Win</div>
            <div className="text-2xl font-bold text-neon-green">${stats.avgWin?.toFixed(2)}</div>
          </div>
          <div className="bg-card-bg rounded border border-surface p-4">
            <div className="text-xs text-muted mb-1">Avg Loss</div>
            <div className="text-2xl font-bold text-neon-red">${stats.avgLoss?.toFixed(2)}</div>
          </div>
          <div className="bg-card-bg rounded border border-surface p-4">
            <div className="text-xs text-muted mb-1">Profit Factor</div>
            <div className="text-2xl font-bold text-neon-cyan">{stats.profitFactor?.toFixed(2)}</div>
          </div>
          <div className="bg-card-bg rounded border border-surface p-4">
            <div className="text-xs text-muted mb-1">Total Trades</div>
            <div className="text-2xl font-bold text-neon-green">{stats.totalTrades}</div>
          </div>
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* P&L Distribution */}
        <div className="bg-card-bg rounded border border-surface p-6">
          <h3 className="text-lg font-semibold mb-4 text-neon-cyan">P&L Distribution</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={pnlChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="range" stroke="#94a3b8" style={{ fontSize: '12px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '12px' }} />
              <Tooltip
                contentStyle={{ backgroundColor: '#111827', border: '1px solid #1e293b' }}
              />
              <Bar dataKey="count" fill="#00e5ff" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Cumulative P&L */}
        <div className="bg-card-bg rounded border border-surface p-6">
          <h3 className="text-lg font-semibold mb-4 text-neon-cyan">Cumulative P&L</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={pnlChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="range" stroke="#94a3b8" style={{ fontSize: '12px' }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: '12px' }} />
              <Tooltip
                contentStyle={{ backgroundColor: '#111827', border: '1px solid #1e293b' }}
              />
              <Line
                type="monotone"
                dataKey="cumulative"
                stroke="#00ff88"
                strokeWidth={2}
                dot={{ fill: '#00ff88', r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-card-bg rounded border border-surface p-6">
        <div className="flex gap-4 mb-6">
          <div className="flex-1">
            <label className="block text-sm text-muted mb-2">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-surface border border-grid rounded px-3 py-2 text-sm text-bright focus:outline-none focus:border-neon-cyan"
            />
          </div>
          <div className="flex-1">
            <label className="block text-sm text-muted mb-2">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-surface border border-grid rounded px-3 py-2 text-sm text-bright focus:outline-none focus:border-neon-cyan"
            />
          </div>
          <div className="flex-1">
            <label className="block text-sm text-muted mb-2">Filter</label>
            <input
              type="text"
              placeholder="Symbol or strategy..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-full bg-surface border border-grid rounded px-3 py-2 text-sm text-bright placeholder-muted focus:outline-none focus:border-neon-cyan"
            />
          </div>
        </div>

        {/* Trades Table */}
        {loading ? (
          <div className="text-center py-4 text-muted">Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-4 text-muted">No trades yet</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-grid">
                <tr className="text-muted">
                  {[
                    { key: 'date', label: 'Date' },
                    { key: 'symbol', label: 'Symbol' },
                    { key: 'side', label: 'Side' },
                    { key: 'qty', label: 'Qty' },
                    { key: 'entryPrice', label: 'Entry' },
                    { key: 'exitPrice', label: 'Exit' },
                    { key: 'pnl', label: 'P&L' },
                    { key: 'pnlPercent', label: 'P&L %' },
                    { key: 'strategy', label: 'Strategy' },
                    { key: 'duration', label: 'Duration' },
                  ].map(({ key, label }) => (
                    <th
                      key={key}
                      onClick={() => handleSort(key)}
                      className="text-left py-3 px-2 cursor-pointer hover:text-neon-cyan transition"
                    >
                      {label}
                      {sortConfig.key === key && (
                        <span className="ml-1">{sortConfig.direction === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((trade, i) => {
                  const isProfit = (trade?.pnl || 0) >= 0
                  return (
                    <tr key={i} className="border-b border-grid hover:bg-surface/50 transition">
                      <td className="py-3 px-2 text-muted text-xs">{trade?.date}</td>
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
                      <td className="py-3 px-2">{trade?.qty}</td>
                      <td className="py-3 px-2">${(trade?.entryPrice || 0).toFixed(2)}</td>
                      <td className="py-3 px-2">${(trade?.exitPrice || 0).toFixed(2)}</td>
                      <td className={clsx(
                        'py-3 px-2 font-semibold',
                        isProfit ? 'text-neon-green' : 'text-neon-red'
                      )}>
                        ${(trade?.pnl || 0).toFixed(2)}
                      </td>
                      <td className={clsx(
                        'py-3 px-2 font-semibold',
                        isProfit ? 'text-neon-green' : 'text-neon-red'
                      )}>
                        {isProfit ? '+' : ''}{(trade?.pnlPercent || 0).toFixed(2)}%
                      </td>
                      <td className="py-3 px-2 text-muted text-xs">{trade?.strategy}</td>
                      <td className="py-3 px-2 text-muted text-xs">{trade?.duration}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
