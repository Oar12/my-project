import { useEffect } from 'react'

interface RealtimeUpdatesProps {
  onStatsUpdate: (stats: any) => void
  onTradeUpdate: () => void
}

export default function RealtimeUpdates({ onStatsUpdate, onTradeUpdate }: RealtimeUpdatesProps) {
  useEffect(() => {
    let ws: WebSocket | null = null
    let reconnectInterval: NodeJS.Timeout | null = null

    const connect = () => {
      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const wsUrl = `${protocol}//${window.location.hostname}:${window.location.port || 8000}/ws`
        
        ws = new WebSocket(wsUrl)

        ws.onopen = () => {
          console.log('WebSocket connected')
          if (reconnectInterval) {
            clearInterval(reconnectInterval)
            reconnectInterval = null
          }
          // Send ping to keep alive
          const pingInterval = setInterval(() => {
            if (ws?.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'ping' }))
            }
          }, 30000)
          
          return () => clearInterval(pingInterval)
        }

        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data)
            
            if (msg.type === 'stats_update') {
              onStatsUpdate(msg.data)
            } else if (msg.type === 'trade_event') {
              onTradeUpdate()
            }
          } catch (err) {
            console.error('Failed to parse WebSocket message:', err)
          }
        }

        ws.onerror = (error) => {
          console.error('WebSocket error:', error)
        }

        ws.onclose = () => {
          console.log('WebSocket disconnected, reconnecting...')
          // Attempt reconnect
          if (!reconnectInterval) {
            reconnectInterval = setInterval(connect, 3000)
          }
        }
      } catch (err) {
        console.error('Failed to connect WebSocket:', err)
      }
    }

    connect()

    return () => {
      if (ws) {
        ws.close()
      }
      if (reconnectInterval) {
        clearInterval(reconnectInterval)
      }
    }
  }, [onStatsUpdate, onTradeUpdate])

  return null
}
