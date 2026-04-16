import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { ChevronDown, ChevronUp, Edit2, Save, X } from 'lucide-react'
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

export default function Strategies() {
  const [strategies, setStrategies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState({})
  const [editingParams, setEditingParams] = useState({})
  const [saving, setSaving] = useState({})

  const { get, post, put } = useApi()

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        const raw = await get('/api/strategies')
        const list = raw?.strategies || (Array.isArray(raw) ? raw : [])
        const data = snakeToCamel(list).map(s => ({
          ...s,
          active: s.enabled ?? s.status === 'active',
          return: s.metrics?.avgPnl ?? 0,
          sharpe: s.metrics?.sharpeRatio ?? 0,
          drawdown: 0,
          tradeCount: s.metrics?.totalTrades ?? 0,
          parameters: {
            riskPerTrade: s.riskPerTrade ?? 0.02,
            positionSize: s.positionSize ?? 0.1,
            maxPositions: s.maxPositions ?? 5,
          },
        }))
        setStrategies(data)
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

  const handleToggle = async (name, currentStatus) => {
    try {
      const endpoint = currentStatus ? 'disable' : 'enable'
      await post(`/api/strategies/${name}/${endpoint}`, {})
      setStrategies(prev => prev.map(s =>
        s.name === name ? { ...s, active: !currentStatus } : s
      ))
    } catch (err) {
      alert(`Error toggling strategy: ${err.message}`)
    }
  }

  const handleEditParam = (name, param, value) => {
    setEditingParams(prev => ({
      ...prev,
      [name]: { ...prev[name], [param]: value }
    }))
  }

  const handleSaveParams = async (name) => {
    try {
      setSaving(prev => ({ ...prev, [name]: true }))
      await put(`/api/strategies/${name}/params`, editingParams[name] || {})
      setStrategies(prev => prev.map(s =>
        s.name === name
          ? { ...s, parameters: editingParams[name] || s.parameters }
          : s
      ))
      setEditingParams(prev => ({ ...prev, [name]: null }))
    } catch (err) {
      alert(`Error saving parameters: ${err.message}`)
    } finally {
      setSaving(prev => ({ ...prev, [name]: false }))
    }
  }

  const toggleExpanded = (name) => {
    setExpanded(prev => ({
      ...prev,
      [name]: !prev[name]
    }))
  }

  if (error) {
    return (
      <div className="p-8 bg-neon-red/10 border border-neon-red rounded text-neon-red">
        Error loading strategies: {error}
      </div>
    )
  }

  return (
    <div className="p-8 space-y-8">
      <h1 className="text-3xl font-bold">Strategies</h1>

      {loading ? (
        <div className="text-center py-4 text-muted">Loading...</div>
      ) : strategies.length === 0 ? (
        <div className="text-center py-4 text-muted">No strategies configured</div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {strategies.map((strategy, i) => (
            <div key={i} className="bg-card-bg rounded border border-surface overflow-hidden">
              {/* Card Header */}
              <div className="p-6 cursor-pointer hover:bg-surface/50 transition">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="text-xl font-semibold">{strategy.name}</h3>
                      <div
                        className={clsx(
                          'px-3 py-1 rounded text-xs font-semibold',
                          strategy.active
                            ? 'bg-neon-green/20 text-neon-green'
                            : 'bg-surface text-muted'
                        )}
                      >
                        {strategy.active ? 'Active' : 'Disabled'}
                      </div>
                    </div>
                    <p className="text-sm text-muted">{strategy.description}</p>
                  </div>

                  <div className="flex items-center gap-4 text-right">
                    <div>
                      <div className="text-2xl font-bold text-neon-green">
                        {(strategy?.return || 0).toFixed(2)}%
                      </div>
                      <div className="text-xs text-muted">Return</div>
                    </div>
                    <div>
                      <div className="text-2xl font-bold text-neon-cyan">
                        {(strategy?.sharpe || 0).toFixed(2)}
                      </div>
                      <div className="text-xs text-muted">Sharpe</div>
                    </div>
                    <div>
                      <div className="text-2xl font-bold text-neon-red">
                        {(strategy?.drawdown || 0).toFixed(1)}%
                      </div>
                      <div className="text-xs text-muted">Max DD</div>
                    </div>
                    <div>
                      <div className="text-2xl font-bold text-bright">
                        {strategy?.tradeCount || 0}
                      </div>
                      <div className="text-xs text-muted">Trades</div>
                    </div>

                    <button
                      onClick={() => toggleExpanded(strategy.name)}
                      className="p-2 hover:bg-surface rounded transition"
                    >
                      {expanded[strategy.name] ? (
                        <ChevronUp className="w-5 h-5" />
                      ) : (
                        <ChevronDown className="w-5 h-5" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Quick Actions */}
                <div className="flex gap-3 mt-4 pt-4 border-t border-grid">
                  <button
                    onClick={() => handleToggle(strategy.name, strategy.active)}
                    className={clsx(
                      'px-4 py-2 rounded text-sm font-semibold transition',
                      strategy.active
                        ? 'bg-neon-red/20 text-neon-red hover:bg-neon-red/30'
                        : 'bg-neon-green/20 text-neon-green hover:bg-neon-green/30'
                    )}
                  >
                    {strategy.active ? 'Disable' : 'Enable'}
                  </button>
                </div>
              </div>

              {/* Expanded Content */}
              {expanded[strategy.name] && (
                <div className="border-t border-grid p-6 space-y-6 bg-darker/50">
                  {/* Performance Chart */}
                  <div>
                    <h4 className="text-lg font-semibold text-neon-cyan mb-4">Performance</h4>
                    <ResponsiveContainer width="100%" height={250}>
                      <LineChart data={strategy.performanceChart || []}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                        <XAxis dataKey="date" stroke="#94a3b8" style={{ fontSize: '12px' }} />
                        <YAxis stroke="#94a3b8" style={{ fontSize: '12px' }} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#111827', border: '1px solid #1e293b' }}
                        />
                        <Line
                          type="monotone"
                          dataKey="value"
                          stroke="#00ff88"
                          strokeWidth={2}
                          dot={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Parameters Editor */}
                  <div>
                    <div className="flex items-center justify-between mb-4">
                      <h4 className="text-lg font-semibold text-neon-cyan">Parameters</h4>
                      {editingParams[strategy.name] && (
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleSaveParams(strategy.name)}
                            disabled={saving[strategy.name]}
                            className="px-4 py-2 bg-neon-green/20 text-neon-green rounded text-sm font-semibold hover:bg-neon-green/30 transition disabled:opacity-50"
                          >
                            {saving[strategy.name] ? 'Saving...' : 'Save'}
                          </button>
                          <button
                            onClick={() => setEditingParams(prev => ({ ...prev, [strategy.name]: null }))}
                            className="px-4 py-2 bg-neon-red/20 text-neon-red rounded text-sm font-semibold hover:bg-neon-red/30 transition"
                          >
                            Cancel
                          </button>
                        </div>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      {Object.entries(strategy.parameters || {}).map(([key, value]) => (
                        <div key={key} className="bg-surface rounded p-3 border border-grid">
                          <label className="block text-xs text-muted mb-2 uppercase">{key}</label>
                          {editingParams[strategy.name] ? (
                            <input
                              type="number"
                              value={editingParams[strategy.name][key] || value}
                              onChange={(e) =>
                                handleEditParam(strategy.name, key, parseFloat(e.target.value))
                              }
                              className="w-full bg-darker border border-grid rounded px-2 py-1 text-bright text-sm focus:outline-none focus:border-neon-cyan"
                            />
                          ) : (
                            <div className="font-semibold text-bright">{value}</div>
                          )}
                        </div>
                      ))}
                    </div>

                    {!editingParams[strategy.name] && (
                      <button
                        onClick={() => setEditingParams(prev => ({
                          ...prev,
                          [strategy.name]: { ...strategy.parameters }
                        }))}
                        className="mt-4 px-4 py-2 bg-neon-cyan/20 text-neon-cyan rounded text-sm font-semibold hover:bg-neon-cyan/30 transition flex items-center gap-2"
                      >
                        <Edit2 className="w-4 h-4" />
                        Edit Parameters
                      </button>
                    )}
                  </div>

                  {/* Recent Signals */}
                  <div>
                    <h4 className="text-lg font-semibold text-neon-cyan mb-4">Recent Signals</h4>
                    <div className="space-y-2">
                      {(strategy.recentSignals || []).slice(0, 5).map((signal, j) => (
                        <div key={j} className="flex items-center justify-between p-3 bg-surface rounded border border-grid">
                          <div>
                            <div className="font-semibold">{signal.symbol}</div>
                            <div className="text-xs text-muted">{signal.timestamp}</div>
                          </div>
                          <div className={clsx(
                            'px-3 py-1 rounded text-xs font-semibold',
                            signal.type === 'BUY'
                              ? 'bg-neon-green/20 text-neon-green'
                              : 'bg-neon-red/20 text-neon-red'
                          )}>
                            {signal.type}
                          </div>
                        </div>
                      ))}
                      {(!strategy.recentSignals || strategy.recentSignals.length === 0) && (
                        <div className="text-center py-4 text-muted">No recent signals</div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
