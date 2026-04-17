interface StatsCardProps {
  title: string
  value: string
  color: 'green' | 'red' | 'blue' | 'purple'
  trend?: string
}

const colorClasses = {
  green: 'text-green-400 bg-green-900/20 border-green-800',
  red: 'text-red-400 bg-red-900/20 border-red-800',
  blue: 'text-blue-400 bg-blue-900/20 border-blue-800',
  purple: 'text-purple-400 bg-purple-900/20 border-purple-800',
}

export default function StatsCard({ title, value, color, trend }: StatsCardProps) {
  return (
    <div className={`rounded-lg border p-6 ${colorClasses[color]}`}>
      <p className="text-sm font-medium text-slate-300 mb-2">{title}</p>
      <p className="text-3xl font-bold mb-2">{value}</p>
      {trend && <p className="text-xs text-slate-400">{trend}</p>}
    </div>
  )
}
