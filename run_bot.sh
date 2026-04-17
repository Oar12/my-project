#!/bin/bash

# Polymarket Trading Bot Startup Script (Linux/Mac/Pi)

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Polymarket Trading Bot Dashboard                         ║"
echo "║   Starting bot with API server and notifications...        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Load .env file if it exists
if [ -f .env ]; then
    echo "[*] Loading environment from .env"
    export $(cat .env | xargs)
fi

# Check if --paper flag is passed
PAPER_MODE=""
if [ "$1" == "--paper" ]; then
    PAPER_MODE="--paper"
    echo "[*] Running in PAPER MODE (no real USDC will be spent)"
else
    echo ""
    echo "⚠️  WARNING: Running in LIVE MODE"
    echo "This will spend real USDC on Polymarket!"
    echo ""
    read -p "Type 'yes' to continue: " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 1
    fi
fi

echo ""
echo "[*] Starting API server on http://0.0.0.0:8000"
echo "[*] Terminal UI running alongside"
echo "[*] Open http://localhost:8000 in browser for dashboard"
echo "[*] (Or visit http://localhost:5173 if npm run dev is running in web/)"
echo ""

# Run the bot
python apps/trend_bot.py $PAPER_MODE
