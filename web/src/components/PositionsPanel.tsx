interface Position {
  id: string
  side: string
  entry_price: number
  size: number
  entry_time: number
  hold_time: number
}

interface PositionsPanelProps {
  positions: Position[]
}

export default function PositionsPanel({ positions }: PositionsPanelProps) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
      <h2 className="text-xl font-bold text-cyan-400 mb-4">📈 Open Positions</h2>
      
      {positions.length === 0 ? (
        <div className="text-center py-8 text-slate-400">
          No open positions
        </div>
      ) : (
        <div className="space-y-3">
          {positions.map((pos) => (
            <div 
              key={pos.id} 
              className="bg-slate-800 border border-slate-700 rounded-lg p-4 flex items-center justify-between"
            >
              <div>
                <p className="text-sm font-medium text-slate-300">
                  {pos.side.toUpperCase()}
                </p>
                <p className="text-xs text-slate-500">
                  Entry: ${pos.entry_price.toFixed(4)}
                </p>
              </div>
              <div className="text-right">
                <p className="text-lg font-mono font-bold text-cyan-300">
                  {pos.size.toFixed(2)} shares
                </p>
                <p className="text-xs text-slate-500">
                  Hold: {pos.hold_time.toFixed(0)}s
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
