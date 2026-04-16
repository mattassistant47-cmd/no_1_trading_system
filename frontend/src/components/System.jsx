import { useEffect, useState, useContext } from 'react'
import { useApi } from '../hooks/useApi'
import { AppContext } from '../App'
import StatusBadge from './common/StatusBadge'
import { AlertCircle, CheckCircle, WifiOff } from 'lucide-react'
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

export default function System() {
  const { wsConnected } = useContext(AppContext)
  const [systemData, setSystemData] = useState(null)
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [logLevel, setLogLevel] = useState('all')
  const [tradingMode, setTradingMode] = useState('paper')
  const [showModeWarning, setShowModeWarning] = useState(false)

  const { get, post } = useApi()

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)

        let systemInfo = null
        try {
          systemInfo = snakeToCamel(await get('/api/system/health'))
          setSystemData(systemInfo)
          setTradingMode(systemInfo?.mode || 'paper')
        } catch (e) {
          setSystemData(null)
        }

        let logData = []
        try {
          logData = snakeToCamel(await get('/api/system/logs?limit=50'))
        } catch (e) { /* logs unavailable */ }
        setLogs(Array.isArray(logData) ? logData : [])

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

  const handleModeChange = async () => {
    if (tradingMode === 'paper') {
      setShowModeWarning(true)
      return
    }

    try {
      const newMode = 'paper'
      await post('/api/system/mode', { mode: newMode })
      setTradingMode(newMode)
      setShowModeWarning(false)
    } catch (err) {
      alert(`Error changing mode: ${err.message}`)
    }
  }

  const handleConfirmLiveMode = async () => {
    try {
      await post('/api/system/mode', { mode: 'live' })
      setTradingMode('live')
      setShowModeWarning(false)
    } catch (err) {
      alert(`Error enabling live mode: ${err.message}`)
    }
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'healthy':
      case 'connected':
      case 'up':
        return 'success'
      case 'degraded':
      case 'warning':
        return 'warning'
      case 'error':
      case 'disconnected':
      case 'down':
        return 'error'
      default:
        return 'neutral'
    }
  }

  const filteredLogs = (logs || []).filter(log => {
    if (logLevel === 'all') return true
    return (log?.level || '').toLowerCase() === logLevel
  })

  if (error && !systemData && logs.length === 0) {
    return (
      <div className="p-8 bg-neon-red/10 border border-neon-red rounded text-neon-red">
        System status unavailable: {error}
      </div>
    )
  }

  return (
    <div className="p-8 space-y-8">
      <h1 className="text-3xl font-bold">System Status</h1>

      {/* Mode Toggle with Warning */}
      {showModeWarning && (
        <div className="bg-neon-red/20 border border-neon-red rounded p-6">
          <div className="flex items-start gap-4">
            <AlertCircle className="w-6 h-6 text-neon-red flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-bold text-neon-red mb-2">Enable Live Trading?</h3>
              <p className="text-sm text-bright mb-4">
                This will enable live trading with real money. Ensure all systems are properly configured and tested.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={handleConfirmLiveMode}
                  className="px-4 py-2 bg-neon-red/30 text-neon-red rounded font-semibold hover:bg-neon-red/40 transition"
                >
                  Confirm Live Mode
                </button>
                <button
                  onClick={() => setShowModeWarning(false)}
                  className="px-4 py-2 bg-surface text-bright rounded font-semibold hover:bg-surface/80 transition"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Trading Mode Card */}
      <div className={clsx(
        'rounded border-2 p-6',
        tradingMode === 'live'
          ? 'bg-neon-red/20 border-neon-red'
          : 'bg-neon-green/20 border-neon-green'
      )}>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm text-muted mb-2">TRADING MODE</div>
            <div className={clsx(
              'text-3xl font-bold',
              tradingMode === 'live' ? 'text-neon-red' : 'text-neon-green'
            )}>
              {tradingMode.toUpperCase()}
            </div>
          </div>
          <button
            onClick={handleModeChange}
            className={clsx(
              'px-6 py-3 rounded font-semibold transition',
              tradingMode === 'live'
                ? 'bg-neon-green/30 text-neon-green hover:bg-neon-green/40'
                : 'bg-neon-red/30 text-neon-red hover:bg-neon-red/40'
            )}
          >
            Switch to {tradingMode === 'live' ? 'Paper' : 'Live'}
          </button>
        </div>
      </div>

      {/* WebSocket Status */}
      <div className={clsx(
        'rounded border-2 p-6',
        wsConnected
          ? 'bg-neon-green/20 border-neon-green'
          : 'bg-neon-red/20 border-neon-red'
      )}>
        <div className="flex items-center gap-3">
          {wsConnected ? (
            <CheckCircle className="w-6 h-6 text-neon-green" />
          ) : (
            <WifiOff className="w-6 h-6 text-neon-red" />
          )}
          <div>
            <div className="text-sm text-muted">WebSocket Connection</div>
            <div className={clsx(
              'font-bold text-lg',
              wsConnected ? 'text-neon-green' : 'text-neon-red'
            )}>
              {wsConnected ? 'Connected' : 'Disconnected'}
            </div>
          </div>
        </div>
      </div>

      {/* Service Health */}
      {systemData && (
        <>
          <div className="bg-card-bg rounded border border-surface p-6">
            <h3 className="text-lg font-semibold text-neon-cyan mb-4">Service Health</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
              {Object.entries(systemData?.services || {}).map(([name, status]) => (
                <div key={name} className="bg-surface rounded p-4 border border-grid">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm font-semibold capitalize">{name}</div>
                    <StatusBadge
                      status={getStatusColor(status)}
                      label={status}
                    />
                  </div>
                  <div className="text-xs text-muted">
                    {status === 'connected' || status === 'healthy'
                      ? 'Operational'
                      : status === 'degraded'
                        ? 'Limited service'
                        : 'Issues detected'}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Resource Usage */}
          <div className="bg-card-bg rounded border border-surface p-6">
            <h3 className="text-lg font-semibold text-neon-cyan mb-4">Resource Usage</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold">CPU Usage</span>
                  <span className="text-neon-cyan">{systemData?.cpu ?? 0}%</span>
                </div>
                <div className="w-full bg-surface rounded-full h-3 overflow-hidden">
                  <div
                    className={clsx(
                      'h-full transition-all',
                      (systemData?.cpu ?? 0) < 60
                        ? 'bg-neon-green'
                        : (systemData?.cpu ?? 0) < 80
                          ? 'bg-yellow-500'
                          : 'bg-neon-red'
                    )}
                    style={{ width: `${systemData?.cpu ?? 0}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold">Memory Usage</span>
                  <span className="text-neon-cyan">{systemData?.memory ?? 0}%</span>
                </div>
                <div className="w-full bg-surface rounded-full h-3 overflow-hidden">
                  <div
                    className={clsx(
                      'h-full transition-all',
                      (systemData?.memory ?? 0) < 60
                        ? 'bg-neon-green'
                        : (systemData?.memory ?? 0) < 80
                          ? 'bg-yellow-500'
                          : 'bg-neon-red'
                    )}
                    style={{ width: `${systemData?.memory ?? 0}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold">Disk Usage</span>
                  <span className="text-neon-cyan">{systemData?.disk ?? 0}%</span>
                </div>
                <div className="w-full bg-surface rounded-full h-3 overflow-hidden">
                  <div
                    className={clsx(
                      'h-full transition-all',
                      (systemData?.disk ?? 0) < 60
                        ? 'bg-neon-green'
                        : (systemData?.disk ?? 0) < 80
                          ? 'bg-yellow-500'
                          : 'bg-neon-red'
                    )}
                    style={{ width: `${systemData?.disk ?? 0}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* System Uptime */}
          <div className="bg-card-bg rounded border border-surface p-6">
            <h3 className="text-lg font-semibold text-neon-cyan mb-4">System Information</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <div className="text-sm text-muted mb-2">Uptime</div>
                <div className="text-2xl font-bold text-neon-green">{systemData?.uptime || 'N/A'}</div>
              </div>
              <div>
                <div className="text-sm text-muted mb-2">Last Update</div>
                <div className="text-2xl font-bold text-neon-cyan">{systemData?.lastUpdate || 'N/A'}</div>
              </div>
            </div>
          </div>

          {/* Scheduler */}
          {(systemData?.scheduler || []).length > 0 && (
            <div className="bg-card-bg rounded border border-surface p-6">
              <h3 className="text-lg font-semibold text-neon-cyan mb-4">Scheduled Jobs</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-grid">
                    <tr className="text-muted">
                      <th className="text-left py-3 px-2">Job</th>
                      <th className="text-left py-3 px-2">Next Run</th>
                      <th className="text-left py-3 px-2">Last Run</th>
                      <th className="text-left py-3 px-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(systemData?.scheduler || []).map((job, i) => (
                      <tr key={i} className="border-b border-grid hover:bg-surface/50 transition">
                        <td className="py-3 px-2 font-semibold">{job?.name}</td>
                        <td className="py-3 px-2 text-muted text-xs">{job?.nextRun}</td>
                        <td className="py-3 px-2 text-muted text-xs">{job?.lastRun}</td>
                        <td className="py-3 px-2">
                          <StatusBadge
                            status={getStatusColor(job.status)}
                            label={job.status}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Logs */}
      <div className="bg-card-bg rounded border border-surface p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-neon-cyan">System Logs</h3>
          <select
            value={logLevel}
            onChange={(e) => setLogLevel(e.target.value)}
            className="bg-surface border border-grid rounded px-3 py-2 text-sm text-bright focus:outline-none focus:border-neon-cyan"
          >
            <option value="all">All Levels</option>
            <option value="debug">Debug</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
          </select>
        </div>

        <div className="bg-darker rounded border border-grid font-mono text-xs max-h-96 overflow-y-auto">
          {filteredLogs.length === 0 ? (
            <div className="p-4 text-muted">No logs found</div>
          ) : (
            filteredLogs.map((log, i) => (
              <div
                key={i}
                className={clsx(
                  'px-4 py-2 border-b border-grid/50 last:border-b-0',
                  log?.level === 'ERROR' ? 'text-neon-red' :
                  log?.level === 'WARNING' ? 'text-yellow-500' :
                  log?.level === 'INFO' ? 'text-neon-cyan' :
                  'text-muted'
                )}
              >
                <span className="text-muted">[{log?.timestamp}]</span>
                {' '}
                <span className="font-semibold">[{log?.level}]</span>
                {' '}
                {log?.message}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
