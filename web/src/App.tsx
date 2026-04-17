import { useEffect, useState } from 'react'
import axios from 'axios'
import StatsCard from './components/StatsCard'
import PositionsPanel from './components/PositionsPanel'
import TradeHistory from './components/TradeHistory'
import ControlPanel from './components/ControlPanel'
import RealtimeUpdates from './components/RealtimeUpdates'

interface Stats {
  total_pnl: number
  win_rate: number
  wins: number
  losses: number
  trades_placed: number
  trades_closed: number
  bankroll: number
  position_count: number
  is_running: boolean
  is_paused?: boolean
  mode: string
  uptime: number
  // Header / feed fields
  coin?: string
  strategy?: string
  market_connected?: boolean
  market_countdown?: string
  btc_price?: number | null
  btc_connected?: boolean
  btc_momentum_30s?: number | null
  btc_volatility_60s?: number | null
  // Orderbook
  up_bid?: number
  up_ask?: number
  up_spread?: number
  down_bid?: number
  down_ask?: number
  down_spread?: number
}

interface Position {
  id: string
  side: string
  entry_price: number
  size: number
  entry_time: number
  hold_time: number
}

interface Trade {
  ts: string
  event: string
  side?: string
  entry_price?: number
  exit_price?: number
  pnl?: number
  outcome?: string
  [key: string]: any
}

export default function App() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch stats and positions
  const fetchData = async () => {
    try {
      const [statsRes, posRes, tradesRes] = await Promise.all([
        axios.get('/api/stats'),
        axios.get('/api/positions'),
        axios.get('/api/trades?limit=20'),
      ])

      setStats(statsRes.data)
      setPositions(posRes.data.positions)
      setTrades(tradesRes.data.trades)
      setError(null)
      setLoading(false)
    } catch (err) {
      setError('Failed to fetch bot data')
      console.error(err)
    }
  }

  // Initial fetch
  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 1000) // Poll every 1 second
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-cyan-400 mx-auto mb-4"></div>
          <p className="text-slate-300">Connecting to bot...</p>
        </div>
      </div>
    )
  }

  if (error && !stats) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error}</p>
          <p className="text-slate-400">Make sure the bot API is running on port 8000</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Real-time updates via WebSocket */}
      <RealtimeUpdates onStatsUpdate={setStats} onTradeUpdate={() => fetchData()} />

      {/* Header */}
      <div className="bg-slate-900 border-b border-slate-800 p-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-3xl font-bold text-cyan-400">
              Mybot
            </h1>
            {/* Running/Mode badges */}
            <div className="flex items-center gap-3">
              <div className={`px-3 py-1 rounded-full text-sm font-medium ${
                stats?.is_running 
                  ? 'bg-green-900 text-green-300' 
                  : 'bg-red-900 text-red-300'
              }`}>
                {stats?.is_running ? '● Running' : '● Stopped'}
              </div>
              <div className="px-3 py-1 rounded-full text-sm font-medium bg-blue-900 text-blue-300">
                {stats?.mode}
              </div>
            </div>
          </div>

          {/* AutoBot status bar */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-mono text-slate-300 mb-2">
            <span className="font-bold text-white">AutoBot</span>
            <span className="text-slate-500">│</span>
            <span>{stats?.coin ?? '—'}</span>
            <span className="text-slate-500">│</span>
            <span>Strategy = <span className="text-cyan-400">{stats?.strategy ?? '—'}</span></span>
            <span className="text-slate-500">│</span>
            <span>Mode = <span className={stats?.mode === 'PAPER' ? 'text-yellow-400' : 'text-red-400'}>{stats?.mode ?? '—'}</span></span>
            <span className="text-slate-500">│</span>
            <span className={stats?.market_connected ? 'text-green-400' : 'text-yellow-400'}>
              {stats?.market_connected ? '● LIVE' : '○ …'}
            </span>
            <span className="text-slate-500">│</span>
            <span>ends in {stats?.market_countdown ?? '--:--'}</span>
            <span className="text-slate-500">│</span>
            <span>up {stats?.uptime ?? '—'}</span>
          </div>

          {/* BTC feed bar */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-mono text-slate-400">
            <span className={stats?.btc_connected ? 'text-green-400' : 'text-yellow-400'}>
              {stats?.btc_connected ? '● Binance' : '○ Binance'}
            </span>
            <span>BTC {stats?.btc_price != null ? `$${stats.btc_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '--'}</span>
            <span className="text-slate-500">│</span>
            <span>
              30s Mom = {stats?.btc_momentum_30s != null
                ? <span className={stats.btc_momentum_30s >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {stats.btc_momentum_30s >= 0 ? '+' : ''}{stats.btc_momentum_30s.toFixed(3)}%
                  </span>
                : '--'}
            </span>
            <span className="text-slate-500">│</span>
            <span>60s Vol = {stats?.btc_volatility_60s != null ? `${stats.btc_volatility_60s.toFixed(3)}%` : '--'}</span>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="max-w-7xl mx-auto p-6 space-y-6">
        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatsCard
            title="Total PnL"
            value={`$${stats?.total_pnl.toFixed(2)}`}
            color={stats?.total_pnl ?? 0 >= 0 ? 'green' : 'red'}
            trend={`${stats?.trades_closed || 0} closed`}
          />
          <StatsCard
            title="Win Rate"
            value={`${stats?.win_rate.toFixed(1)}%`}
            color={stats?.win_rate ?? 0 >= 50 ? 'green' : 'red'}
            trend={`${stats?.wins || 0}W / ${stats?.losses || 0}L`}
          />
          <StatsCard
            title="Bankroll"
            value={`$${stats?.bankroll.toFixed(2)}`}
            color="blue"
            trend={`Started: $${stats?.total_pnl ? (stats.bankroll - stats.total_pnl).toFixed(2) : '100.00'}`}
          />
          <StatsCard
            title="Open Positions"
            value={String(stats?.position_count || 0)}
            color="purple"
            trend={`${stats?.trades_placed || 0} entered`}
          />
        </div>

        {/* Orderbook */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-3 uppercase tracking-wider">Orderbook</h2>
          <table className="w-full text-sm font-mono">
            <thead>
              <tr className="text-slate-400 text-right">
                <th className="text-left font-medium pb-2"></th>
                <th className="pb-2 pr-8">UP</th>
                <th className="pb-2">DOWN</th>
              </tr>
            </thead>
            <tbody className="text-slate-200">
              <tr>
                <td className="text-slate-400 py-1">Bid</td>
                <td className="text-right pr-8">{stats?.up_bid != null && stats.up_bid > 0 ? stats.up_bid.toFixed(4) : '--'}</td>
                <td className="text-right">{stats?.down_bid != null && stats.down_bid > 0 ? stats.down_bid.toFixed(4) : '--'}</td>
              </tr>
              <tr>
                <td className="text-slate-400 py-1">Ask</td>
                <td className="text-right pr-8">{stats?.up_ask != null && stats.up_ask > 0 ? stats.up_ask.toFixed(4) : '--'}</td>
                <td className="text-right">{stats?.down_ask != null && stats.down_ask > 0 ? stats.down_ask.toFixed(4) : '--'}</td>
              </tr>
              <tr>
                <td className="text-slate-400 py-1">Spread</td>
                <td className="text-right pr-8">{stats?.up_spread != null && stats.up_spread > 0 ? stats.up_spread.toFixed(4) : '--'}</td>
                <td className="text-right">{stats?.down_spread != null && stats.down_spread > 0 ? stats.down_spread.toFixed(4) : '--'}</td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Positions, Trade History, and Controls */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <div className="lg:col-span-3 flex flex-col gap-6">
            <PositionsPanel positions={positions} />
            <TradeHistory trades={trades} />
          </div>
          <div className="lg:col-span-2">
            <ControlPanel stats={stats} />
          </div>
        </div>
      </div>
    </div>
  )
}
