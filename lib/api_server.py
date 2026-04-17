"""
REST API and WebSocket server for the trading bot.
Exposes bot state and allows remote control/monitoring.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import uvicorn

logger = logging.getLogger("api_server")

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
FRONTEND_DIST = WEB_ROOT / "dist"


class BotStateManager:
    """Manages shared state between bot and API."""

    def __init__(self):
        self.current_stats: Dict[str, Any] = {
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "wins": 0,
            "losses": 0,
            "trades_placed": 0,
            "trades_closed": 0,
            "bankroll": 0.0,
            "position_count": 0,
            "is_running": False,
            "mode": "UNKNOWN",
            "uptime": 0.0,
        }
        self.current_positions: List[Dict[str, Any]] = []
        self.recent_trades: List[Dict[str, Any]] = []
        self.settings: Dict[str, Any] = {}
        self.pending_settings_update: Dict[str, Any] = {}
        self.subscribers: Set[WebSocket] = set()
        # Control flags polled by the bot's main loop
        self.stop_requested: bool = False
        self.pause_requested: bool = False
        self.close_all_requested: bool = False
        self.close_winners_requested: bool = False
        self.close_losers_requested: bool = False

    async def broadcast_trade(self, trade_event: Dict[str, Any]) -> None:
        """Broadcast a trade event to all connected WebSocket clients."""
        if not self.subscribers:
            return

        message = json.dumps({"type": "trade_event", "data": trade_event})
        dead = set()
        for ws in self.subscribers:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)

        self.subscribers -= dead

    async def broadcast_stats_update(self) -> None:
        """Broadcast current stats to all connected clients."""
        if not self.subscribers:
            return

        message = json.dumps({"type": "stats_update", "data": self.current_stats})
        dead = set()
        for ws in self.subscribers:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)

        self.subscribers -= dead


class APIServer:
    """FastAPI server for bot monitoring and control."""

    def __init__(self, state_manager: BotStateManager):
        self.state = state_manager
        self.app = FastAPI(title="Polymarket Bot API", version="1.0.0")
        self._setup_routes()
        self._setup_middleware()

    def _setup_middleware(self):
        """Setup CORS and other middleware."""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _setup_routes(self):
        """Setup all API routes."""

        @self.app.get("/api/stats")
        async def get_stats():
            """Get current bot statistics."""
            return self.state.current_stats

        @self.app.get("/api/positions")
        async def get_positions():
            """Get all open positions."""
            return {"positions": self.state.current_positions}

        @self.app.get("/api/trades")
        async def get_trades(limit: int = 50):
            """Get recent trades (read from trade_log.jsonl)."""
            trades = []
            trade_log_path = Path("trade_log.jsonl")
            if trade_log_path.exists():
                with open(trade_log_path, "r") as f:
                    lines = f.readlines()
                    for line in lines[-limit:]:
                        try:
                            trades.append(json.loads(line.strip()))
                        except json.JSONDecodeError:
                            pass
            return {"trades": trades[::-1]}  # newest first

        @self.app.get("/api/settings")
        async def get_settings():
            """Get current bot settings."""
            return self.state.settings

        @self.app.post("/api/settings")
        async def update_settings(updates: Dict[str, Any]):
            """Queue runtime settings updates for the bot loop to apply safely."""
            allowed = {
                "trend_threshold",
                "min_hold_time",
                "size_usdc",
                "min_spread",
                "cooldown",
                "take_profit",
                "stop_loss",
                "max_positions",
            }
            invalid = [k for k in updates.keys() if k not in allowed]
            if invalid:
                return {
                    "status": "error",
                    "detail": f"Unsupported setting(s): {', '.join(invalid)}",
                }

            self.state.pending_settings_update.update(updates)
            self.state.settings.update(updates)
            return {"status": "queued", "settings": self.state.settings}

        @self.app.post("/api/control/{action}")
        async def control_bot(action: str):
            """Control bot actions (stop, pause, resume, flatten, etc)."""
            if action == "stop":
                self.state.stop_requested = True
                self.state.pause_requested = False
                return {"status": "stop_requested"}
            elif action == "pause":
                self.state.pause_requested = True
                return {"status": "pause_requested"}
            elif action == "resume":
                self.state.pause_requested = False
                return {"status": "resumed"}
            elif action == "flatten":
                self.state.close_all_requested = True
                return {"status": "flatten_requested"}
            elif action == "take_profits":
                self.state.close_winners_requested = True
                return {"status": "close_winners_requested"}
            elif action == "cut_losses":
                self.state.close_losers_requested = True
                return {"status": "close_losers_requested"}
            return {"status": "error", "detail": "Unknown action"}

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket connection for real-time updates."""
            await websocket.accept()
            self.state.subscribers.add(websocket)
            logger.info(f"WebSocket client connected. Total: {len(self.state.subscribers)}")

            try:
                while True:
                    # Keep connection alive; messages from client are control commands
                    data = await websocket.receive_text()
                    try:
                        msg = json.loads(data)
                        if msg.get("type") == "ping":
                            await websocket.send_text('{"type":"pong"}')
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                logger.debug(f"WebSocket error: {e}")
            finally:
                self.state.subscribers.discard(websocket)
                logger.info(f"WebSocket client disconnected. Total: {len(self.state.subscribers)}")

        @self.app.get("/api/health")
        async def health():
            """Health check."""
            return {"status": "ok", "timestamp": datetime.now().isoformat()}

        self._setup_frontend_routes()

    def _setup_frontend_routes(self) -> None:
        """Serve the built dashboard, or a setup page if it has not been built yet."""
        if FRONTEND_DIST.exists():
            assets_dir = FRONTEND_DIST / "assets"
            if assets_dir.exists():
                self.app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

            @self.app.get("/favicon.ico", include_in_schema=False)
            async def serve_favicon():
                favicon_path = FRONTEND_DIST / "favicon.ico"
                if favicon_path.exists():
                    return FileResponse(str(favicon_path))
                return HTMLResponse(status_code=204, content="")

            @self.app.get("/", include_in_schema=False)
            async def serve_index():
                return FileResponse(str(FRONTEND_DIST / "index.html"))

            @self.app.get("/{full_path:path}", include_in_schema=False)
            async def serve_spa(full_path: str):
                requested_path = (FRONTEND_DIST / full_path).resolve()
                try:
                    requested_path.relative_to(FRONTEND_DIST.resolve())
                except ValueError:
                    return HTMLResponse(status_code=404, content="Not Found")
                if requested_path.is_file():
                    return FileResponse(str(requested_path))
                return FileResponse(str(FRONTEND_DIST / "index.html"))
        else:
            @self.app.get("/", response_class=HTMLResponse, include_in_schema=False)
            async def dashboard_not_built():
                return HTMLResponse(
                    content="""
<!doctype html>
<html lang=\"en\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>Dashboard Not Built</title>
        <style>
            :root {
                color-scheme: dark;
                --bg: #08111f;
                --panel: #0f1b2d;
                --border: #1e3553;
                --text: #e5eefb;
                --muted: #94a9c6;
                --accent: #5eead4;
                --warn: #fbbf24;
            }
            body {
                margin: 0;
                min-height: 100vh;
                display: grid;
                place-items: center;
                background:
                    radial-gradient(circle at top, #12304f 0, transparent 35%),
                    linear-gradient(160deg, var(--bg), #050b14 72%);
                color: var(--text);
                font: 16px/1.5 Segoe UI, system-ui, sans-serif;
            }
            main {
                width: min(760px, calc(100vw - 32px));
                background: rgba(15, 27, 45, 0.92);
                border: 1px solid var(--border);
                border-radius: 18px;
                padding: 28px;
                box-shadow: 0 18px 60px rgba(0, 0, 0, 0.35);
            }
            h1 {
                margin: 0 0 12px;
                font-size: clamp(28px, 4vw, 40px);
            }
            p { margin: 0 0 14px; color: var(--muted); }
            code {
                display: inline-block;
                padding: 2px 8px;
                border-radius: 999px;
                background: #0a1525;
                border: 1px solid var(--border);
                color: var(--accent);
            }
            pre {
                overflow-x: auto;
                margin: 18px 0;
                padding: 16px;
                border-radius: 12px;
                background: #07101d;
                border: 1px solid var(--border);
                color: var(--text);
            }
            .note {
                margin-top: 18px;
                padding: 14px 16px;
                border-radius: 12px;
                border: 1px solid rgba(251, 191, 36, 0.35);
                background: rgba(251, 191, 36, 0.08);
                color: #fde68a;
            }
            a { color: var(--accent); }
        </style>
    </head>
    <body>
        <main>
            <h1>Dashboard frontend is not built yet</h1>
            <p>The API server is running, but it cannot serve the React dashboard because <code>web/dist</code> does not exist.</p>
            <p>Build the frontend from the project root:</p>
            <pre>cd web
npm install
npm run build</pre>
            <p>Then reload <code>http://localhost:8000</code>.</p>
            <div class=\"note\">For local development, you can also run <code>npm run dev</code> in <code>web</code> and open <a href=\"http://localhost:5173\">http://localhost:5173</a>.</div>
        </main>
    </body>
</html>
                    """.strip()
                )

    async def run(self, host: str = "0.0.0.0", port: int = 8000):
        """Run the server."""
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
        )
        server = uvicorn.Server(config)
        await server.serve()


# Singleton instance
_state_manager: Optional[BotStateManager] = None
_api_server: Optional[APIServer] = None


def get_state_manager() -> BotStateManager:
    """Get or create the global state manager."""
    global _state_manager
    if _state_manager is None:
        _state_manager = BotStateManager()
    return _state_manager


def get_api_server() -> APIServer:
    """Get or create the global API server."""
    global _api_server
    if _api_server is None:
        _api_server = APIServer(get_state_manager())
    return _api_server
