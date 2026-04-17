import { useEffect, useState } from 'react'
import axios from 'axios'

interface Stats {
  is_running?: boolean
  is_paused?: boolean
  mode?: string
}

export default function ControlPanel({ stats }: { stats: Stats | null }) {
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [form, setForm] = useState({
    trend_threshold: '0.50',
    min_hold_time: '5.0',
    size_usdc: '100.0',
    min_spread: '0.04',
    cooldown: '10.0',
  })

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const res = await axios.get('/api/settings')
        const s = res.data || {}
        setForm({
          trend_threshold: String(s.trend_threshold ?? 0.5),
          min_hold_time: String(s.min_hold_time ?? 5.0),
          size_usdc: String(s.size_usdc ?? 100.0),
          min_spread: String(s.min_spread ?? 0.04),
          cooldown: String(s.cooldown ?? 10.0),
        })
      } catch {
        // Ignore; defaults remain.
      }
    }
    loadSettings()
  }, [])

  const handleControl = async (action: string) => {
    setLoading(true)
    try {
      const response = await axios.post(`/api/control/${action}`)
      setMessage(`${action}: ${response.data.status}`)
      setTimeout(() => setMessage(null), 3000)
    } catch (err) {
      setMessage('Error sending command')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const applySettings = async () => {
    setLoading(true)
    try {
      const payload = {
        trend_threshold: Number(form.trend_threshold),
        min_hold_time: Number(form.min_hold_time),
        size_usdc: Number(form.size_usdc),
        min_spread: Number(form.min_spread),
        cooldown: Number(form.cooldown),
      }
      const response = await axios.post('/api/settings', payload)
      setMessage(`settings: ${response.data.status}`)
      setTimeout(() => setMessage(null), 3000)
    } catch (err) {
      setMessage('Error updating settings')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const isPaused = stats?.is_paused ?? false
  const isRunning = stats?.is_running ?? false

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
      <h2 className="text-xl font-bold text-cyan-400 mb-4">Controls</h2>

      <div className="space-y-3">
        {isPaused ? (
          <button
            onClick={() => handleControl('resume')}
            disabled={loading || !isRunning}
            className="w-full bg-green-900 hover:bg-green-800 disabled:opacity-50 text-green-300 font-medium py-2 px-4 rounded-lg transition"
          >
            ▶ Resume Trading
          </button>
        ) : (
          <button
            onClick={() => handleControl('pause')}
            disabled={loading || !isRunning}
            className="w-full bg-yellow-900 hover:bg-yellow-800 disabled:opacity-50 text-yellow-300 font-medium py-2 px-4 rounded-lg transition"
          >
            ⏸ Pause Trading
          </button>
        )}

        <button
          onClick={() => handleControl('take_profits')}
          disabled={loading || !isRunning}
          className="w-full bg-emerald-900 hover:bg-emerald-800 disabled:opacity-50 text-emerald-300 font-medium py-2 px-4 rounded-lg transition"
        >
          ✅ Close Winners
        </button>

        <button
          onClick={() => handleControl('cut_losses')}
          disabled={loading || !isRunning}
          className="w-full bg-orange-900 hover:bg-orange-800 disabled:opacity-50 text-orange-300 font-medium py-2 px-4 rounded-lg transition"
        >
          🩹 Cut Losers
        </button>

        <button
          onClick={() => handleControl('flatten')}
          disabled={loading || !isRunning}
          className="w-full bg-rose-900 hover:bg-rose-800 disabled:opacity-50 text-rose-300 font-medium py-2 px-4 rounded-lg transition"
        >
          ⏏ Flatten All Positions
        </button>

        <button
          onClick={() => handleControl('stop')}
          disabled={loading || !isRunning}
          className="w-full bg-red-900 hover:bg-red-800 disabled:opacity-50 text-red-300 font-medium py-2 px-4 rounded-lg transition"
        >
          ⛔ Stop Bot
        </button>
      </div>

      <div className="mt-6 pt-6 border-t border-slate-700">
        <h3 className="text-sm font-medium text-slate-300 mb-3">Runtime Parameters</h3>
        <div className="grid grid-cols-1 gap-3">
          <label className="text-xs text-slate-400">
            Trend Threshold (0-1)
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={form.trend_threshold}
              onChange={(e) => setForm({ ...form, trend_threshold: e.target.value })}
              className="mt-1 w-full rounded bg-slate-800 border border-slate-700 px-3 py-2 text-slate-200"
            />
          </label>

          <label className="text-xs text-slate-400">
            Min Hold Time (sec)
            <input
              type="number"
              step="0.5"
              min="0"
              value={form.min_hold_time}
              onChange={(e) => setForm({ ...form, min_hold_time: e.target.value })}
              className="mt-1 w-full rounded bg-slate-800 border border-slate-700 px-3 py-2 text-slate-200"
            />
          </label>

          <label className="text-xs text-slate-400">
            Size USDC
            <input
              type="number"
              step="1"
              min="1"
              value={form.size_usdc}
              onChange={(e) => setForm({ ...form, size_usdc: e.target.value })}
              className="mt-1 w-full rounded bg-slate-800 border border-slate-700 px-3 py-2 text-slate-200"
            />
          </label>

          <label className="text-xs text-slate-400">
            Min Spread
            <input
              type="number"
              step="0.001"
              min="0"
              value={form.min_spread}
              onChange={(e) => setForm({ ...form, min_spread: e.target.value })}
              className="mt-1 w-full rounded bg-slate-800 border border-slate-700 px-3 py-2 text-slate-200"
            />
          </label>

          <label className="text-xs text-slate-400">
            Cooldown (sec)
            <input
              type="number"
              step="0.5"
              min="0"
              value={form.cooldown}
              onChange={(e) => setForm({ ...form, cooldown: e.target.value })}
              className="mt-1 w-full rounded bg-slate-800 border border-slate-700 px-3 py-2 text-slate-200"
            />
          </label>

          <button
            onClick={applySettings}
            disabled={loading || !isRunning}
            className="w-full bg-cyan-900 hover:bg-cyan-800 disabled:opacity-50 text-cyan-300 font-medium py-2 px-4 rounded-lg transition"
          >
            Apply Runtime Settings
          </button>
        </div>
      </div>

      {message && (
        <div className="mt-4 p-3 bg-slate-800 border border-slate-700 rounded text-sm text-slate-300">
          {message}
        </div>
      )}

      {/* Settings Info */}
      <div className="mt-6 pt-6 border-t border-slate-700">
        <h3 className="text-sm font-medium text-slate-400 mb-3">API Status</h3>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
          <p className="text-sm text-slate-300">Connected</p>
        </div>
      </div>
    </div>
  )
}
