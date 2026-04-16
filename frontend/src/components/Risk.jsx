import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import { AlertCircle } from 'lucide-react'
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

export default function Risk() {
  const [riskData, setRiskData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const { get } = useApi()

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        const data = await get('/api/risk/overview')
        setRiskData(snakeToCamel(data || {}))
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

  const getColor = (value, thresholds) => {
    if (value <= thresholds.good) return '#00ff88'
    if (value <= thresholds.warning) return '#ffaa00'
    return '#ff3366'
  }

  const getRiskStatus = (value, max) => {
    const percent = (value / max) * 100
    if (percent <= 50) return 'safe'
    if (percent <= 75) return 'warning'
    return 'danger'
  }

  if (error) {
    return (
      <div className="p-8 bg-neon-red/10 border border-neon-red rounded text-neon-red">
        Error loading risk data: {error}
      </div>
    )
  }

  if (loading || !riskData) {
    return <div className="p-8 text-muted">Loading...</div>
  }

  const {
    drawdown = 5.2,
    maxDrawdown = 15,
    dailyLoss = 2.5,
    maxDailyLoss = 10,
    exposure = 65,
    maxExposure = 100,
    circuitBreakerStatus = 'armed',
    correlationMatrix = [],
    varMetrics = [],
    alerts = [],
  } = riskData

  return (
    <div className="p-8 space-y-8">
      <h1 className="text-3xl font-bold">Risk Monitoring</h1>

      {/* Circuit Breaker Status */}
      <div className={clsx(
        'rounded border-2 p-8 text-center',
        circuitBreakerStatus === 'active'
          ? 'bg-neon-red/20 border-neon-red'
          : circuitBreakerStatus === 'tripped'
            ? 'bg-neon-red/30 border-neon-red animate-pulse'
            : 'bg-neon-green/20 border-neon-green'
      )}>
        <div className="text-sm text-muted mb-2">CIRCUIT BREAKER</div>
        <div className={clsx(
          'text-5xl font-bold mb-2',
          circuitBreakerStatus === 'armed' ? 'text-neon-green' :
          circuitBreakerStatus === 'active' ? 'text-neon-red' :
          'text-neon-red'
        )}>
          {circuitBreakerStatus.toUpperCase()}
        </div>
        {circuitBreakerStatus === 'tripped' && (
          <div className="text-sm text-neon-red mt-2">All trading halted - reset required</div>
        )}
      </div>

      {/* Risk Gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Drawdown Gauge */}
        <div className="bg-card-bg rounded border border-surface p-6">
          <div className="text-sm text-muted mb-4">Current Drawdown</div>
          <div className="text-center mb-4">
            <div className="text-3xl font-bold text-neon-red mb-2">{(drawdown || 0).toFixed(1)}%</div>
            <div className="text-xs text-muted">Max: {maxDrawdown || 0}%</div>
          </div>
          <div className="w-full bg-surface rounded-full h-3 overflow-hidden">
            <div
              className={clsx(
                'h-full transition-all',
                getRiskStatus(drawdown, maxDrawdown) === 'safe'
                  ? 'bg-neon-green'
                  : getRiskStatus(drawdown, maxDrawdown) === 'warning'
                    ? 'bg-yellow-500'
                    : 'bg-neon-red'
              )}
              style={{ width: `${(drawdown / maxDrawdown) * 100}%` }}
            />
          </div>
        </div>

        {/* Daily Loss Gauge */}
        <div className="bg-card-bg rounded border border-surface p-6">
          <div className="text-sm text-muted mb-4">Daily Loss</div>
          <div className="text-center mb-4">
            <div className="text-3xl font-bold text-neon-red mb-2">${(dailyLoss || 0).toFixed(2)}</div>
            <div className="text-xs text-muted">Max: ${maxDailyLoss || 0}</div>
          </div>
          <div className="w-full bg-surface rounded-full h-3 overflow-hidden">
            <div
              className={clsx(
                'h-full transition-all',
                getRiskStatus(dailyLoss, maxDailyLoss) === 'safe'
                  ? 'bg-neon-green'
                  : getRiskStatus(dailyLoss, maxDailyLoss) === 'warning'
                    ? 'bg-yellow-500'
                    : 'bg-neon-red'
              )}
              style={{ width: `${(dailyLoss / maxDailyLoss) * 100}%` }}
            />
          </div>
        </div>

        {/* Exposure Gauge */}
        <div className="bg-card-bg rounded border border-surface p-6">
          <div className="text-sm text-muted mb-4">Total Exposure</div>
          <div className="text-center mb-4">
            <div className="text-3xl font-bold text-neon-cyan mb-2">{(exposure || 0).toFixed(1)}%</div>
            <div className="text-xs text-muted">Max: {maxExposure || 0}%</div>
          </div>
          <div className="w-full bg-surface rounded-full h-3 overflow-hidden">
            <div
              className={clsx(
                'h-full transition-all',
                getRiskStatus(exposure, maxExposure) === 'safe'
                  ? 'bg-neon-green'
                  : getRiskStatus(exposure, maxExposure) === 'warning'
                    ? 'bg-yellow-500'
                    : 'bg-neon-red'
              )}
              style={{ width: `${(exposure / maxExposure) * 100}%` }}
            />
          </div>
        </div>
      </div>

      {/* Risk Limits */}
      <div className="bg-card-bg rounded border border-surface p-6">
        <h3 className="text-lg font-semibold text-neon-cyan mb-6">Risk Limits Status</h3>
        <div className="space-y-4">
          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="font-semibold">Daily Loss Limit</span>
              <span className="text-sm text-muted">${(dailyLoss || 0).toFixed(2)} / ${maxDailyLoss || 0}</span>
            </div>
            <div className="h-2 bg-surface rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-neon-green via-yellow-500 to-neon-red transition-all"
                style={{ width: `${(dailyLoss / maxDailyLoss) * 100}%` }}
              />
            </div>
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="font-semibold">Max Drawdown Limit</span>
              <span className="text-sm text-muted">{(drawdown || 0).toFixed(1)}% / {maxDrawdown || 0}%</span>
            </div>
            <div className="h-2 bg-surface rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-neon-green via-yellow-500 to-neon-red transition-all"
                style={{ width: `${(drawdown / maxDrawdown) * 100}%` }}
              />
            </div>
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="font-semibold">Position Exposure</span>
              <span className="text-sm text-muted">{(exposure || 0).toFixed(1)}% / {maxExposure || 0}%</span>
            </div>
            <div className="h-2 bg-surface rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-neon-green via-yellow-500 to-neon-red transition-all"
                style={{ width: `${(exposure / maxExposure) * 100}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Alerts */}
      {alerts && alerts.length > 0 && (
        <div className="bg-card-bg rounded border border-surface p-6">
          <h3 className="text-lg font-semibold text-neon-red mb-4 flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            Risk Alerts
          </h3>
          <div className="space-y-3">
            {alerts.map((alert, i) => (
              <div
                key={i}
                className={clsx(
                  'p-4 rounded border',
                  alert.severity === 'critical'
                    ? 'bg-neon-red/20 border-neon-red'
                    : alert.severity === 'warning'
                      ? 'bg-yellow-500/20 border-yellow-500'
                      : 'bg-neon-cyan/20 border-neon-cyan'
                )}
              >
                <div className="font-semibold mb-1">{alert.message}</div>
                <div className="text-xs text-muted">{alert.timestamp}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* VaR Metrics */}
      {varMetrics && varMetrics.length > 0 && (
        <div className="bg-card-bg rounded border border-surface p-6">
          <h3 className="text-lg font-semibold text-neon-cyan mb-4">Value at Risk Metrics</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {varMetrics.map((metric, i) => (
              <div key={i} className="bg-surface rounded p-4 border border-grid">
                <div className="text-xs text-muted mb-2 uppercase">{metric.name}</div>
                <div className="text-2xl font-bold text-neon-red">${(metric?.value || 0).toFixed(2)}</div>
                <div className="text-xs text-muted mt-2">{metric?.confidence || 0}% confidence</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Correlation Matrix */}
      {correlationMatrix && correlationMatrix.length > 0 && (
        <div className="bg-card-bg rounded border border-surface p-6">
          <h3 className="text-lg font-semibold text-neon-cyan mb-4">Asset Correlation Matrix</h3>
          <div className="overflow-x-auto">
            <table className="text-sm">
              <tbody>
                {(correlationMatrix || []).map((row, i) => (
                  <tr key={i}>
                    {(row || []).map((value, j) => {
                      const v = value || 0
                      const color = v < -0.5 ? '#00ff88' : v < 0.5 ? '#667eea' : '#ff3366'
                      return (
                        <td
                          key={j}
                          className="p-2 border border-grid text-center font-mono"
                          style={{ backgroundColor: `${color}20` }}
                        >
                          {v.toFixed(2)}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
