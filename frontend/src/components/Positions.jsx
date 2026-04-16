import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import DataTable from './common/DataTable'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { Trash2 } from 'lucide-react'
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

export default function Positions() {
  const [positions, setPositions] = useState([])
  const [exposureData, setExposureData] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sortConfig, setSortConfig] = useState({ key: 'symbol', direction: 'asc' })
  const [filter, setFilter] = useState('')

  const { get, post } = useApi()

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        const data = await get('/api/positions')
        let exposure = {}
        try { exposure = await get('/api/positions/exposure') } catch (e) { /* optional */ }
        setPositions(snakeToCamel(Array.isArray(data) ? data : []))
        setExposureData(snakeToCamel(exposure || {}))
        setError(null)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 3000)
    return () => clearInterval(interval)
  }, [get])

  const handleSort = (key) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }))
  }

  const handleClosePosition = async (id, symbol) => {
    if (!confirm(`Close ${symbol} position?`)) return
    try {
      await post(`/api/positions/${id}/close`, {})
      setPositions(prev => prev.filter(p => p.id !== id))
    } catch (err) {
      alert(`Error closing position: ${err.message}`)
    }
  }

  let sorted = [...positions]
  if (sortConfig.key) {
    sorted.sort((a, b) => {
      const aVal = a[sortConfig.key]
      const bVal = b[sortConfig.key]
      const comparison = aVal > bVal ? 1 : -1
      return sortConfig.direction === 'asc' ? comparison : -comparison
    })
  }

  const filtered = sorted.filter(p =>
    (p?.symbol || '').toLowerCase().includes(filter.toLowerCase()) ||
    (p?.strategy || '').toLowerCase().includes(filter.toLowerCase())
  )

  if (error) {
    return (
      <div className="p-8 bg-neon-red/10 border border-neon-red rounded text-neon-red">
        Error loading positions: {error}
      </div>
    )
  }

  const exposureChartData = [
    { name: 'Long', value: exposureData.longExposure || 0 },
    { name: 'Short', value: exposureData.shortExposure || 0 },
    { name: 'Net', value: exposureData.netExposure || 0 },
  ]

  return (
    <div className="p-8 space-y-8">
      <h1 className="text-3xl font-bold">Positions</h1>

      {/* Exposure Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-card-bg rounded border border-surface p-6">
          <div className="text-sm text-muted mb-2">Total Exposure</div>
          <div className="text-2xl font-bold text-neon-cyan">
            {exposureData.totalExposure?.toFixed(1) || '0'}%
          </div>
          <div className="text-xs text-muted mt-2">Max: {exposureData.maxExposure || '100'}%</div>
        </div>
        <div className="bg-card-bg rounded border border-surface p-6">
          <div className="text-sm text-muted mb-2">Long Exposure</div>
          <div className="text-2xl font-bold text-neon-green">
            {exposureData.longExposure?.toFixed(1) || '0'}%
          </div>
        </div>
        <div className="bg-card-bg rounded border border-surface p-6">
          <div className="text-sm text-muted mb-2">Short Exposure</div>
          <div className="text-2xl font-bold text-neon-red">
            {exposureData.shortExposure?.toFixed(1) || '0'}%
          </div>
        </div>
      </div>

      {/* Exposure Chart */}
      <div className="bg-card-bg rounded border border-surface p-6">
        <h3 className="text-lg font-semibold mb-4 text-neon-cyan">Exposure Breakdown</h3>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={exposureChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="name" stroke="#94a3b8" />
            <YAxis stroke="#94a3b8" />
            <Tooltip
              contentStyle={{ backgroundColor: '#111827', border: '1px solid #1e293b' }}
            />
            <Bar dataKey="value" fill="#00e5ff" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Positions Table */}
      <div className="bg-card-bg rounded border border-surface p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-neon-cyan">Open Positions ({filtered.length})</h3>
          <input
            type="text"
            placeholder="Filter by symbol or strategy..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="bg-surface border border-grid rounded px-3 py-2 text-sm text-bright placeholder-muted focus:outline-none focus:border-neon-cyan"
          />
        </div>

        {loading ? (
          <div className="text-center py-4 text-muted">Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-4 text-muted">No open positions</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-grid">
                <tr className="text-muted">
                  {[
                    { key: 'symbol', label: 'Symbol' },
                    { key: 'qty', label: 'Qty' },
                    { key: 'entryPrice', label: 'Entry Price' },
                    { key: 'currentPrice', label: 'Current Price' },
                    { key: 'unrealizedPnL', label: 'Unrealized P&L' },
                    { key: 'percentChange', label: '% Change' },
                    { key: 'strategy', label: 'Strategy' },
                    { key: 'portfolioPercent', label: '% Portfolio' },
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
                  <th className="text-left py-3 px-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((pos, i) => {
                  const isProfit = (pos?.unrealizedPnL || 0) >= 0
                  return (
                    <tr key={i} className="border-b border-grid hover:bg-surface/50 transition">
                      <td className="py-3 px-2 font-semibold text-bright">{pos?.symbol}</td>
                      <td className="py-3 px-2">{pos?.qty}</td>
                      <td className="py-3 px-2">${(pos?.entryPrice || 0).toFixed(2)}</td>
                      <td className="py-3 px-2">${(pos?.currentPrice || 0).toFixed(2)}</td>
                      <td className={clsx(
                        'py-3 px-2 font-semibold',
                        isProfit ? 'text-neon-green' : 'text-neon-red'
                      )}>
                        ${(pos?.unrealizedPnL || 0).toFixed(2)}
                      </td>
                      <td className={clsx(
                        'py-3 px-2 font-semibold',
                        isProfit ? 'text-neon-green' : 'text-neon-red'
                      )}>
                        {isProfit ? '+' : ''}{(pos?.percentChange || 0).toFixed(2)}%
                      </td>
                      <td className="py-3 px-2 text-muted text-xs">{pos?.strategy}</td>
                      <td className="py-3 px-2">{(pos?.portfolioPercent || 0).toFixed(1)}%</td>
                      <td className="py-3 px-2">
                        <button
                          onClick={() => handleClosePosition(pos?.id, pos?.symbol)}
                          className="text-neon-red hover:text-neon-red/80 transition p-1"
                          title="Close position"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
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
