# Polymarket Bot Reference Guide

## What This Repo Includes

- BTC trend-following trading bot with paper and live modes
- FastAPI server exposing bot state and control endpoints
- React dashboard with real-time updates
- Discord and Telegram notifications
- Trade logging to `trade_log.jsonl`
- Scripts for local startup and initial credential setup

## Main Entry Points

- `apps/trend_bot.py`: main automated strategy runner
- `scripts/setup.py`: creates `config.yaml` and encrypted credentials
- `lib/api_server.py`: REST and WebSocket API for dashboard/control
- `lib/notifications.py`: Discord and Telegram notifications
- `web/`: dashboard frontend

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
npm install --prefix web
```

### 2. Set up credentials

```bash
python scripts/setup.py
```

### 3. Run paper mode first

```bash
python apps/trend_bot.py --paper
```

When the bot is running you should have:

- Terminal UI with live bot status
- API server on `http://localhost:8000`
- WebSocket updates for the dashboard
- Trade logging to `trade_log.jsonl`

### 4. Open the dashboard

- Default integrated dashboard: `http://localhost:8000`
- Frontend dev server:

```bash
npm run dev --prefix web
```

Then open `http://localhost:5173`.

## Environment Variables

Create a `.env` file in the repo root as needed:

```env
# Live trading
POLY_PRIVATE_KEY=0x...
POLY_SAFE_ADDRESS=0x...

# Optional builder credentials
POLY_BUILDER_API_KEY=...
POLY_BUILDER_API_SECRET=...
POLY_BUILDER_API_PASSPHRASE=...

# Notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Core Commands

### Paper trading

```bash
python apps/trend_bot.py --paper
```

### Live trading

```bash
python apps/trend_bot.py
```

### Frontend development

```bash
npm run dev --prefix web
```

### Frontend production build

```bash
npm run build --prefix web
```

### Syntax check

```bash
python -m py_compile apps/trend_bot.py lib/notifications.py lib/api_server.py
```

## API Reference

The bot exposes these main endpoints:

```text
GET  /api/stats
GET  /api/positions
GET  /api/trades?limit=50
GET  /api/settings
POST /api/control/pause
POST /api/control/stop
WS   /ws
```

## Runtime Architecture

```text
Browser dashboard
    -> REST + WebSocket
FastAPI server (port 8000)
    -> shared state and control
Trading bot (apps/trend_bot.py)
    -> notifications and trade logging
Discord / Telegram
```

Order flow summary:

1. Market data is tracked through `lib/market_manager.py`.
2. `apps/trend_bot.py` records prices and evaluates the strategy.
3. Entry guards check cooldown, spread, expiry, price-band safety, and capacity.
4. Paper mode creates simulated positions locally.
5. Live mode submits signed orders through the trading client stack.
6. Positions and results are logged locally, and the dashboard is updated in real time.

## Notifications

Supported channels:

- Discord via webhook
- Telegram via bot token and chat ID

Notifications can be sent on:

- Bot startup and shutdown
- Trade entry
- Trade exit with PnL

## Testing Checklist

Use this as the default smoke test after setup or changes:

1. Run `python apps/trend_bot.py --paper`.
2. Confirm the terminal shows the bot running and the API server starting.
3. Open `http://localhost:8000` and verify the dashboard loads.
4. Confirm stats update without refreshing.
5. Let paper mode run long enough to produce at least one trade.
6. Check `trade_log.jsonl` for recorded trade activity.
7. If notifications are configured, verify a test alert or live event arrives.

## Operational Checks

Useful commands while the bot is running:

```bash
tail -f trade_log.jsonl
sudo systemctl status polybot
sudo journalctl -u polybot -f
```

On Windows, use PowerShell equivalents for log inspection if needed.

## Pi Zero 2 Deployment

Basic deployment flow:

```bash
pip install -r requirements.txt
npm install --prefix web
npm run build --prefix web
python apps/trend_bot.py --paper
```

Typical `systemd` shape:

```ini
[Unit]
Description=Polymarket Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/mybot
EnvironmentFile=/home/pi/mybot/.env
ExecStart=/home/pi/mybot/.venv/bin/python apps/trend_bot.py --paper
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Safety Notes

- Validate changes in paper mode before live trading.
- Start live trading with small size only.
- Paper and live paths are materially different; do not assume parity without checking both.
- Live exits are not fully implemented end-to-end; local close logic exists, but live sell execution should be treated as incomplete unless verified in code.
- Do not create or keep local live positions if order submission fails.
- Monitor cooldown, spread, minimum hold time, take-profit, and stop-loss interactions when changing strategy behavior.

## Troubleshooting

### Bot will not start

```bash
pip install -r requirements.txt --upgrade
python -m py_compile apps/trend_bot.py lib/notifications.py lib/api_server.py
```

### Dashboard cannot connect

- Make sure the bot is still running.
- Confirm the API server started on port 8000.
- Check whether another process is already using the port.

### WebSocket disconnects often

- Check network stability.
- Reduce dashboard refresh frequency if the device is resource-constrained.

### High CPU or memory use on Pi Zero 2

- Use the built frontend instead of the dev server.
- Reduce refresh activity if needed.
- Monitor with `htop` or service logs.

## Recommended Workflow

1. Set up credentials and dependencies.
2. Run paper mode.
3. Verify dashboard and logs.
4. Configure notifications.
5. Review `trade_log.jsonl` after enough runtime.
6. Only then consider a small live trade.

## Related Docs

- `web/README.md` for frontend-specific details
- `.github/copilot-instructions.md` for repo conventions and trading-risk notes