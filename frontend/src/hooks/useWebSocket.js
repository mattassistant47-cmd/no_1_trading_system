import { useEffect, useRef, useCallback, useState } from 'react'

export const useWebSocket = (url, onMessage, onStatusChange) => {
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)
  const reconnectAttempts = useRef(0)
  const [connected, setConnected] = useState(false)

  const connect = useCallback(() => {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const wsUrl = `${protocol}//${window.location.host}${url}`

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('WebSocket connected')
        setConnected(true)
        onStatusChange?.(true)
        reconnectAttempts.current = 0
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current)
          reconnectTimeoutRef.current = null
        }
        // Subscribe to default channels
        ws.send(JSON.stringify({ type: 'subscribe', channel: 'portfolio' }))
        ws.send(JSON.stringify({ type: 'subscribe', channel: 'trades' }))
        ws.send(JSON.stringify({ type: 'subscribe', channel: 'signals' }))
        ws.send(JSON.stringify({ type: 'subscribe', channel: 'alerts' }))
        ws.send(JSON.stringify({ type: 'subscribe', channel: 'system' }))
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          // Backend sends: {type: "connected"|"pong"|"portfolio_update"|..., channel?: "...", data?: {...}}
          if (data.type === 'connected' || data.type === 'pong' || data.type === 'heartbeat') {
            return // control messages, ignore
          }
          if (data.type === 'subscription_confirmed') {
            return
          }
          // Forward data messages to handler
          const channel = data.channel || data.type || 'system'
          const payload = data.data || data
          onMessage?.(channel, payload)
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err)
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }

      ws.onclose = (event) => {
        console.log('WebSocket disconnected', event.code)
        setConnected(false)
        onStatusChange?.(false)
        wsRef.current = null
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000)
        reconnectAttempts.current += 1
        reconnectTimeoutRef.current = setTimeout(connect, delay)
      }
    } catch (err) {
      console.error('Failed to connect WebSocket:', err)
      setConnected(false)
      onStatusChange?.(false)
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000)
      reconnectAttempts.current += 1
      reconnectTimeoutRef.current = setTimeout(connect, delay)
    }
  }, [url, onMessage, onStatusChange])

  useEffect(() => {
    connect()

    // Send ping every 25 seconds to keep connection alive
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, 25000)

    return () => {
      clearInterval(pingInterval)
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [connect])

  const subscribe = useCallback((channel, callback) => {
    // Send subscribe message to backend
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'subscribe', channel }))
    }
    return () => {}
  }, [])

  const send = useCallback((type, data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, ...data }))
    }
  }, [])

  return {
    connected,
    subscribe,
    send,
  }
}
