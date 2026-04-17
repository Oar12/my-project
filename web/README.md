# Polymarket Bot Dashboard

A modern, real-time web dashboard for monitoring and controlling your Polymarket trading bot.

## Features

- 📊 **Live Stats**: Real-time PnL, win rate, bankroll tracking
- 📈 **Open Positions**: View current open trades with entry prices and hold times
- 📜 **Trade History**: Complete trade log with entry/exit prices and outcomes
- ⚡ **Real-time Updates**: WebSocket connection for instant trade notifications
- 🎛️ **Bot Control**: Pause or stop the bot from the dashboard
- 📱 **Responsive**: Works on desktop, tablet, and mobile
- 🎨 **Beautiful UI**: Dark theme optimized for long trading sessions

## Setup

### Prerequisites

- Node.js 18+ and npm
- The bot running with the API server enabled (port 8000)

### Installation

```bash
cd web

# Install dependencies
npm install

# Development (with hot reload)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

### Environment Setup

The dashboard connects to the API server on `http://localhost:8000` by default.

For production deployment, update the API endpoint in the Vite config:

```js
// vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://<your-pi-ip>:8000',
      changeOrigin: true,
    },
  }
}
```

## Running on Pi Zero 2

### Option 1: Development Server (Recommended for Local Testing)

```bash
cd web
npm run dev
```

Access at: `http://localhost:5173`

### Option 2: Production Build (Recommended for Deployment)

```bash
cd web
npm run build
```

This creates a `dist/` folder. The bot's API server automatically serves this when built.

Access at: `http://<pi-ip>:8000/`

### Using Docker (Optional)

For easier deployment on Pi Zero 2, you can build a Docker container that includes both the bot and dashboard.

## WebSocket Connection

The dashboard automatically connects to the WebSocket server at `/ws` for real-time updates:

- **Trade events**: Instantly see new entries and exits
- **Stats updates**: Real-time PnL, win rate changes
- **Auto-reconnect**: Handles connection drops gracefully

## API Endpoints

The dashboard communicates with these API endpoints:

- `GET /api/stats` - Current bot statistics
- `GET /api/positions` - Open positions
- `GET /api/trades?limit=50` - Trade history
- `GET /api/settings` - Current bot settings
- `POST /api/control/{action}` - Control bot (pause, stop)
- `WS /ws` - Real-time updates

## Troubleshooting

### Dashboard shows "Failed to fetch bot data"

- Make sure the bot is running: `python apps/trend_bot.py --paper`
- Check that the API server started (should see "API Server running" message)
- Verify port 8000 is not blocked by a firewall

### WebSocket connection keeps dropping

- This is normal on unstable networks; the dashboard auto-reconnects
- Check your network connection if frequent drops occur

### Slow performance on Pi Zero 2

- Ensure Pi has adequate RAM (at least 512MB free)
- Kill other services if needed
- Consider increasing the polling interval in `App.tsx` from 2 seconds to 5 seconds

## Development

### Project Structure

```
web/
├── src/
│   ├── App.tsx             # Main app component
│   ├── main.tsx            # Entry point
│   ├── index.css           # Global styles
│   └── components/
│       ├── StatsCard.tsx       # Stat display card
│       ├── PositionsPanel.tsx  # Open positions view
│       ├── TradeHistory.tsx    # Trade log table
│       ├── ControlPanel.tsx    # Bot controls
│       └── RealtimeUpdates.tsx # WebSocket handler
├── index.html              # HTML template
├── vite.config.ts          # Vite configuration
├── tsconfig.json           # TypeScript config
├── tailwind.config.js      # Tailwind CSS config
└── package.json            # Dependencies
```

### Adding New Features

1. **New metric**: Add to `StatsCard` in `App.tsx`
2. **New control**: Add button in `ControlPanel.tsx`
3. **New chart**: Use Recharts library (already installed)

### Styling

Uses **Tailwind CSS** for all styling. Classes follow this pattern:

- Colors: `text-cyan-400`, `bg-slate-900`
- Spacing: `p-6`, `mb-4`, `gap-4`
- Responsive: `md:grid-cols-2`, `lg:col-span-2`

## Performance Notes for Pi Zero 2

✅ **Optimized for low resources**:
- Minimal JavaScript bundle (~200KB)
- Efficient WebSocket updates
- Lazy rendering
- CSS-only animations (no CPU-heavy JavaScript animations)

### Build Size

```
prod/dist/index.html      ~5KB
prod/dist/index.js      ~200KB (gzipped)
prod/dist/index.css      ~20KB (gzipped)
```

Total gzipped: ~225KB (very light!)

## License

Same as parent project.
