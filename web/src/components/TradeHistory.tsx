import { formatDistanceToNow } from 'date-fns'

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

interface TradeHistoryProps {
  trades: Trade[]
}

export default function TradeHistory({ trades }: TradeHistoryProps) {
  const filteredTrades = trades.filter(t => ['ENTER', 'EXIT'].includes(t.event))

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
      <h2 className="text-xl font-bold text-cyan-400 mb-4">📊 Trade History</h2>
      
      {filteredTrades.length === 0 ? (
        <div className="text-center py-8 text-slate-400">
          No trades yet
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="text-left py-2 px-4 text-slate-400 font-medium">Time</th>
                <th className="text-left py-2 px-4 text-slate-400 font-medium">Event</th>
                <th className="text-left py-2 px-4 text-slate-400 font-medium">Side</th>
                <th className="text-right py-2 px-4 text-slate-400 font-medium">Price</th>
                <th className="text-right py-2 px-4 text-slate-400 font-medium">PnL</th>
                <th className="text-center py-2 px-4 text-slate-400 font-medium">Outcome</th>
              </tr>
            </thead>
            <tbody>
              {filteredTrades.map((trade, idx) => (
                <tr key={idx} className="border-b border-slate-800 hover:bg-slate-800/50">
                  <td className="py-3 px-4 text-slate-300">
                    {formatDistanceToNow(new Date(trade.ts), { addSuffix: true })}
                  </td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      trade.event === 'ENTER'
                        ? 'bg-blue-900 text-blue-300'
                        : 'bg-purple-900 text-purple-300'
                    }`}>
                      {trade.event}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-mono text-slate-300">
                    {trade.side?.toUpperCase() || '—'}
                  </td>
                  <td className="py-3 px-4 text-right font-mono text-slate-300">
                    {trade.event === 'ENTER' 
                      ? trade.entry_price?.toFixed(4)
                      : trade.exit_price?.toFixed(4) || '—'
                    }
                  </td>
                  <td className={`py-3 px-4 text-right font-mono font-bold ${
                    trade.pnl !== undefined && trade.pnl >= 0
                      ? 'text-green-400'
                      : trade.pnl !== undefined
                      ? 'text-red-400'
                      : 'text-slate-400'
                  }`}>
                    {trade.pnl !== undefined ? `${trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}` : '—'}
                  </td>
                  <td className="py-3 px-4 text-center">
                    {trade.outcome === 'WIN' ? (
                      <span className="px-2 py-1 bg-green-900 text-green-300 rounded text-xs font-medium">
                        ✓ Win
                      </span>
                    ) : trade.outcome === 'LOSS' ? (
                      <span className="px-2 py-1 bg-red-900 text-red-300 rounded text-xs font-medium">
                        ✗ Loss
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
