import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { createContext, useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import Positions from './components/Positions'
import Trades from './components/Trades'
import Strategies from './components/Strategies'
import Risk from './components/Risk'
import System from './components/System'
import { useWebSocket } from './hooks/useWebSocket'

export const AppContext = createContext()

export default function App() {
  const [wsConnected, setWsConnected] = useState(false)
  const [realtimeData, setRealtimeData] = useState({
    portfolio: null,
    trades: [],
    signals: [],
    alerts: [],
    system: null,
  })

  const handleWsMessage = (channel, data) => {
    setRealtimeData(prev => ({
      ...prev,
      [channel]: data
    }))
  }

  useWebSocket('/ws', handleWsMessage, (connected) => {
    setWsConnected(connected)
  })

  return (
    <AppContext.Provider value={{ wsConnected, realtimeData }}>
      <Router>
        <div className="flex h-screen bg-dark-bg text-bright">
          <Sidebar />
          <main className="flex-1 overflow-auto bg-darker">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/positions" element={<Positions />} />
              <Route path="/trades" element={<Trades />} />
              <Route path="/strategies" element={<Strategies />} />
              <Route path="/risk" element={<Risk />} />
              <Route path="/system" element={<System />} />
            </Routes>
          </main>
        </div>
      </Router>
    </AppContext.Provider>
  )
}
