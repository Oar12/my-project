# Dashboard Development Course
### Built from the Mybot Trading Dashboard — FastAPI + React + TypeScript + Tailwind

---

## Table of Contents

1. [How the Web Works](#1-how-the-web-works)
2. [JSON — The Language Between Frontend and Backend](#2-json)
3. [Python Basics Refresher](#3-python-basics-refresher)
4. [FastAPI — Building the Backend](#4-fastapi)
5. [REST APIs — Designing Endpoints](#5-rest-apis)
6. [WebSockets — Real-Time Communication](#6-websockets)
7. [HTML & CSS — The Skeleton](#7-html--css)
8. [JavaScript — Making Pages Dynamic](#8-javascript)
9. [TypeScript — JavaScript with Types](#9-typescript)
10. [React — Building UIs with Components](#10-react)
11. [Tailwind CSS — Styling Without Writing CSS](#11-tailwind-css)
12. [Axios — HTTP Requests from the Browser](#12-axios)
13. [Vite — The Build Tool](#13-vite)
14. [Putting It All Together — The Full Dashboard](#14-putting-it-all-together)

---

## 1. How the Web Works

Before writing a single line of code, understand the flow:

```
Browser (React app)  ←——HTTP/WebSocket——→  Server (FastAPI)  ←——→  Bot logic
```

- The **browser** is the **frontend** — what the user sees.
- The **server** is the **backend** — where data lives and logic runs.
- They talk over **HTTP** (request/response) or **WebSocket** (persistent two-way channel).

**Request/Response cycle (HTTP):**
1. Browser sends: `GET http://localhost:8000/api/stats`
2. Server receives the request, looks up the data, and sends back a **response**.
3. Browser reads the response and updates the screen.

**Key terms:**
| Term | Meaning |
|------|---------|
| URL | The address of a resource, e.g. `/api/stats` |
| HTTP Method | What to do — `GET` (read), `POST` (send/update) |
| Status Code | Result — `200 OK`, `404 Not Found`, `500 Server Error` |
| Header | Metadata attached to a request/response |
| Body | The actual data payload (usually JSON) |

---

## 2. JSON

JSON (JavaScript Object Notation) is the data format used everywhere in the dashboard.

**Example — what `/api/stats` returns:**
```json
{
  "total_pnl": 12.50,
  "win_rate": 62.5,
  "wins": 10,
  "losses": 6,
  "bankroll": 512.00,
  "is_running": true,
  "mode": "PAPER"
}
```

**Rules:**
- Keys are always strings in double quotes: `"total_pnl"`
- Values can be: strings `"PAPER"`, numbers `12.50`, booleans `true/false`, arrays `[...]`, objects `{...}`, or `null`
- No trailing commas
- No comments

**In Python**, you convert between JSON and Python objects like this:
```python
import json

# Python dict → JSON string
data = {"pnl": 12.5, "running": True}
json_string = json.dumps(data)  # '{"pnl": 12.5, "running": true}'

# JSON string → Python dict
parsed = json.loads('{"pnl": 12.5}')
print(parsed["pnl"])  # 12.5
```

**In JavaScript/TypeScript**, JSON is built-in:
```ts
const text = '{"pnl": 12.5}'
const obj = JSON.parse(text)   // → { pnl: 12.5 }
const back = JSON.stringify(obj) // → '{"pnl":12.5}'
```

---

## 3. Python Basics Refresher

Key Python patterns used in `lib/api_server.py`:

### Classes
```python
class BotStateManager:
    def __init__(self):           # runs when you create an instance
        self.is_running = False   # self = "this object"
        self.positions = []

state = BotStateManager()
state.is_running = True
```

### Type hints
```python
from typing import Dict, List, Any, Set

def process(data: Dict[str, Any]) -> List[str]:
    ...
```

### `async` / `await`
FastAPI uses async functions. Think of them as functions that can pause and wait without blocking the whole program.
```python
async def get_stats():
    return {"pnl": 12.5}  # FastAPI automatically turns this into JSON
```

### `Path` (file paths)
```python
from pathlib import Path

log_path = Path("trade_log.jsonl")
if log_path.exists():
    with open(log_path, "r") as f:
        lines = f.readlines()
```

---

## 4. FastAPI

FastAPI is a Python web framework. It takes a function you write and turns it into an HTTP endpoint automatically.

### Install
```bash
pip install fastapi uvicorn
```

### Minimal working server
```python
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/api/hello")
async def hello():
    return {"message": "Hello, world!"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Visit `http://localhost:8000/api/hello` and you get:
```json
{"message": "Hello, world!"}
```

### How it's structured in our bot

We wrap FastAPI in a class so it has access to the shared state:
```python
class APIServer:
    def __init__(self, state_manager: BotStateManager):
        self.state = state_manager
        self.app = FastAPI()
        self._setup_routes()

    def _setup_routes(self):
        @self.app.get("/api/stats")
        async def get_stats():
            return self.state.current_stats  # just return the dict
```

`self.state` is shared with the bot loop — the bot writes to it, the API reads from it.

### CORS Middleware

Browsers block requests to different origins (ports count as different origins). CORS middleware tells the browser "it's fine":
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # allow all origins (fine for local dev)
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Without this, the React app on port `5173` cannot talk to the API on port `8000`.

### Auto-generated docs

FastAPI gives you a free interactive API explorer at:
- `http://localhost:8000/docs` — Swagger UI
- `http://localhost:8000/redoc` — ReDoc

---

## 5. REST APIs

REST is a convention for designing URLs and how HTTP methods map to actions.

| HTTP Method | Purpose | Example |
|------------|---------|---------|
| `GET` | Read data | `GET /api/stats` |
| `POST` | Create or trigger | `POST /api/control/pause` |
| `PUT` | Replace entirely | `PUT /api/settings` |
| `PATCH` | Partial update | `PATCH /api/settings` |
| `DELETE` | Delete | `DELETE /api/positions/abc123` |

### Our endpoints

```python
@app.get("/api/stats")          # → returns current bot stats dict
@app.get("/api/positions")      # → returns {"positions": [...]}
@app.get("/api/trades")         # → reads trade_log.jsonl, returns newest first
@app.get("/api/settings")       # → returns current strategy params
@app.post("/api/settings")      # → updates strategy params safely
@app.post("/api/control/{action}") # → triggers stop/pause/resume/flatten
```

### Path parameters
```python
@app.post("/api/control/{action}")
async def control_bot(action: str):   # FastAPI extracts {action} from the URL
    if action == "pause":
        self.state.pause_requested = True
```

### Query parameters
```python
@app.get("/api/trades")
async def get_trades(limit: int = 50):   # ?limit=20 in the URL
    ...
    for line in lines[-limit:]:
```

Called as: `GET /api/trades?limit=20`

### Input validation / allowlist

Never trust what the client sends. We check settings keys against an allowlist:
```python
allowed = {"trend_threshold", "min_hold_time", "size_usdc", "min_spread", "cooldown"}
invalid = [k for k in updates.keys() if k not in allowed]
if invalid:
    return {"status": "error", "detail": f"Unsupported: {', '.join(invalid)}"}
```

---

## 6. WebSockets

HTTP is one-way (browser asks, server answers). WebSockets open a persistent two-way channel — the server can push data any time.

### Why we use them

Without WebSockets, the frontend polls every second:
```ts
setInterval(fetchData, 1000)  // 1 request/sec even when nothing changed
```

With WebSockets, the server pushes instantly when a trade happens:
```
Server: trade just closed → push {"type": "trade_event", "data": {...}}
```

### Server side (FastAPI)
```python
from fastapi import WebSocket

subscribers: Set[WebSocket] = set()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()         # complete the handshake
    subscribers.add(websocket)
    try:
        while True:
            data = await websocket.receive_text()  # keep alive / handle pings
            if json.loads(data).get("type") == "ping":
                await websocket.send_text('{"type":"pong"}')
    except Exception:
        pass
    finally:
        subscribers.discard(websocket)  # clean up on disconnect
```

### Broadcasting to all clients
```python
async def broadcast_stats_update(self) -> None:
    message = json.dumps({"type": "stats_update", "data": self.current_stats})
    dead = set()
    for ws in self.subscribers:
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)          # remove broken connections
    self.subscribers -= dead
```

### Client side (browser)
```ts
const ws = new WebSocket('ws://localhost:8000/ws')

ws.onopen = () => console.log('connected')

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data)
  if (msg.type === 'stats_update') {
    setStats(msg.data)   // React state update
  }
}

ws.onclose = () => {
  // reconnect after 3 seconds
  setTimeout(connect, 3000)
}
```

This is exactly what `RealtimeUpdates.tsx` does.

---

## 7. HTML & CSS

HTML defines structure; CSS defines appearance.

### HTML skeleton
```html
<!DOCTYPE html>
<html>
  <head>
    <title>My Dashboard</title>
    <link rel="stylesheet" href="style.css">
  </head>
  <body>
    <h1>Total PnL</h1>
    <p class="value">$12.50</p>
  </body>
</html>
```

### CSS basics
```css
.value {
  font-size: 32px;
  font-weight: bold;
  color: #4ade80;   /* green */
}

.card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 24px;
}
```

**The Box Model** — every HTML element is a rectangle:
```
┌─────────────────────────┐
│         margin          │
│  ┌───────────────────┐  │
│  │      border       │  │
│  │  ┌─────────────┐  │  │
│  │  │   padding   │  │  │
│  │  │  [content]  │  │  │
│  │  └─────────────┘  │  │
│  └───────────────────┘  │
└─────────────────────────┘
```

**Flexbox** — the layout system used everywhere in the dashboard:
```css
.row {
  display: flex;
  align-items: center;    /* vertical align */
  gap: 12px;              /* space between items */
}
```

**Grid** — for the stats card row:
```css
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr); /* 4 equal columns */
  gap: 16px;
}
```

---

## 8. JavaScript

JavaScript makes pages interactive. Key concepts used in the dashboard:

### Variables
```js
const name = "Mybot"    // can't be reassigned
let count = 0            // can be reassigned
```

### Functions (including arrow functions)
```js
function fetchData() { ... }

// Arrow function (same thing, shorter syntax)
const fetchData = async () => {
  const response = await fetch('/api/stats')
  const data = await response.json()
}
```

### Async / Await
Everything that talks to a server takes time. `async/await` lets you write it like normal code:
```js
// Without async/await (callback hell)
fetch('/api/stats').then(res => res.json()).then(data => { ... })

// With async/await (clean)
const res = await fetch('/api/stats')
const data = await res.json()
```

### Arrays
```js
const trades = [
  { pnl: 5.0, side: "UP" },
  { pnl: -2.0, side: "DOWN" },
]

// Loop
trades.forEach(t => console.log(t.pnl))

// Filter
const winners = trades.filter(t => t.pnl > 0)

// Map (transform)
const pnls = trades.map(t => t.pnl)  // [5.0, -2.0]
```

### Template literals
```js
const price = 84500.25
console.log(`BTC: $${price.toFixed(2)}`)  // "BTC: $84500.25"
```

### Optional chaining (`?.`)
Used everywhere to safely access properties that might not exist:
```js
const price = stats?.btc_price ?? '--'
// If stats is null → '--'
// If stats.btc_price is null → '--'
// Otherwise → the price
```

---

## 9. TypeScript

TypeScript adds a type system on top of JavaScript. The browser doesn't understand TypeScript — Vite compiles it to JavaScript before serving.

### Why use it?
- Catches bugs before runtime: `stats.btc_pric` → TypeScript error immediately
- Autocomplete in your editor
- Self-documenting code

### Basic types
```ts
const name: string = "Mybot"
const count: number = 42
const running: boolean = true
const prices: number[] = [84000, 84100, 84050]
```

### Interfaces — defining the shape of an object
```ts
interface Stats {
  total_pnl: number
  win_rate: number
  is_running: boolean
  mode: string
  btc_price?: number | null    // ? means optional
}
```

This is exactly the `Stats` interface in `App.tsx`. When you write `stats.total_pnl`, TypeScript knows it's a `number`.

### Union types
```ts
type Color = 'green' | 'red' | 'blue' | 'purple'
// variable can only be one of those four values
```

Used in `StatsCard.tsx`:
```ts
interface StatsCardProps {
  color: 'green' | 'red' | 'blue' | 'purple'
}
```

### Generics
```ts
const [stats, setStats] = useState<Stats | null>(null)
// useState<Stats | null> means: this state holds Stats or null
```

---

## 10. React

React is a library for building UIs from reusable **components**. Each component is a function that returns HTML (called JSX).

### The simplest component
```tsx
export default function Hello() {
  return <h1>Hello, world!</h1>
}
```

### JSX — HTML inside JavaScript
```tsx
const name = "Mybot"
return <h1 className="title">Welcome to {name}</h1>
//                            ^ { } inserts a JS expression
```

Note: use `className` not `class` (reserved word in JS).

### Props — passing data into a component
```tsx
// Define the component
interface StatsCardProps {
  title: string
  value: string
}

export default function StatsCard({ title, value }: StatsCardProps) {
  return (
    <div>
      <p>{title}</p>
      <p>{value}</p>
    </div>
  )
}

// Use it
<StatsCard title="Total PnL" value="$12.50" />
```

This is exactly `StatsCard.tsx`.

### State — data that changes
```tsx
import { useState } from 'react'

export default function Counter() {
  const [count, setCount] = useState(0)  // initial value = 0
  
  return (
    <button onClick={() => setCount(count + 1)}>
      Clicked {count} times
    </button>
  )
}
```

When `setCount` is called, React re-renders the component automatically.

### In our dashboard:
```tsx
const [stats, setStats] = useState<Stats | null>(null)
const [positions, setPositions] = useState<Position[]>([])
const [trades, setTrades] = useState<Trade[]>([])
```

### useEffect — side effects (fetching, subscriptions)
```tsx
import { useEffect } from 'react'

useEffect(() => {
  // runs after the component mounts
  fetchData()
  const interval = setInterval(fetchData, 1000)
  
  return () => {
    // cleanup: runs when component unmounts
    clearInterval(interval)
  }
}, [])  // [] = run once on mount
```

This is the polling loop in `App.tsx`.

### Conditional rendering
```tsx
{stats?.is_running ? (
  <span className="text-green-400">● Running</span>
) : (
  <span className="text-red-400">● Stopped</span>
)}
```

### Rendering lists
```tsx
{positions.map((pos) => (
  <div key={pos.id}>       {/* key is required — helps React track items */}
    {pos.side} — {pos.size} shares
  </div>
))}
```

This is `PositionsPanel.tsx`.

### Component composition (building the layout)
```tsx
// App.tsx composes everything
return (
  <div>
    <RealtimeUpdates onStatsUpdate={setStats} onTradeUpdate={fetchData} />
    <StatsCard title="PnL" value="$12.50" color="green" />
    <PositionsPanel positions={positions} />
    <TradeHistory trades={trades} />
    <ControlPanel stats={stats} />
  </div>
)
```

---

## 11. Tailwind CSS

Tailwind replaces writing CSS files. Instead, you apply utility classes directly on the element.

### Side-by-side comparison

**Normal CSS:**
```css
.card {
  background-color: #1e293b;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 24px;
}
```

**Tailwind:**
```tsx
<div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
```

Same result, no CSS file needed.

### Key patterns used in the dashboard

**Layout:**
```tsx
className="flex items-center gap-4"           // flex row, vertically centered, 16px gap
className="grid grid-cols-4 gap-4"            // 4-column grid
className="min-h-screen"                       // full viewport height
className="max-w-7xl mx-auto"                 // centered container, max 1280px wide
className="space-y-6"                         // 24px vertical gap between children
```

**Colors:**
```tsx
className="text-cyan-400"      // cyan text
className="bg-slate-950"       // very dark background
className="border-slate-800"   // dark border
className="text-green-400"     // green text
className="text-red-400"       // red text
```

**Text:**
```tsx
className="text-3xl font-bold"     // large bold text
className="text-sm font-mono"      // small monospace
className="text-xs text-slate-400" // tiny muted text
```

**Conditional classes (dynamic styling based on state):**
```tsx
className={stats?.mode === 'PAPER' ? 'text-yellow-400' : 'text-red-400'}
```

**Opacity modifier:**
```tsx
className="bg-green-900/20"   // green-900 at 20% opacity
```

### Install
```bash
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init
```

---

## 12. Axios

Axios is an HTTP client — it makes requests to the backend and returns the response data.

### Install
```bash
npm install axios
```

### GET request
```ts
import axios from 'axios'

const res = await axios.get('/api/stats')
const stats = res.data   // already parsed JSON
```

### POST request (sending data)
```ts
await axios.post('/api/settings', {
  trend_threshold: 0.5,
  size_usdc: 100.0,
})
```

### POST with no body (control actions)
```ts
await axios.post('/api/control/pause')
```

### Error handling
```ts
try {
  const res = await axios.get('/api/stats')
  setStats(res.data)
} catch (err) {
  setError('Failed to fetch bot data')
  console.error(err)
}
```

### Fetching multiple endpoints at once
```ts
const [statsRes, posRes, tradesRes] = await Promise.all([
  axios.get('/api/stats'),
  axios.get('/api/positions'),
  axios.get('/api/trades?limit=20'),
])
```

`Promise.all` fires all three requests simultaneously and waits for all to finish — faster than doing them one by one.

---

## 13. Vite

Vite is the build tool. It does two things:
1. **Dev mode** — serves the frontend instantly with hot-reload (`npm run dev`)
2. **Build mode** — bundles everything into optimised static files (`npm run build` → `dist/`)

### Why the proxy matters

In dev mode, the React app runs on `http://localhost:5173` and the FastAPI backend on `http://localhost:8000`. The browser would block cross-origin requests — but Vite's dev proxy forwards `/api` and `/ws` to port 8000 transparently:

```ts
// vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
    '/ws': {
      target: 'ws://localhost:8000',
      ws: true,
    }
  }
}
```

So `axios.get('/api/stats')` in dev mode goes through Vite → FastAPI. In production (built), FastAPI serves the `dist/` folder directly, so there's no cross-origin issue at all.

### Commands
```bash
npm run dev      # start dev server with hot-reload
npm run build    # build to dist/ for production
npm run preview  # preview the production build locally
```

---

## 14. Putting It All Together

### The full data flow — from bot to browser

```
Bot loop writes:
  state.current_stats["btc_price"] = 84500.25
  state.current_stats["is_running"] = True

↓

FastAPI GET /api/stats:
  return self.state.current_stats
  → {"btc_price": 84500.25, "is_running": true, ...}

↓

App.tsx polls every 1s:
  const res = await axios.get('/api/stats')
  setStats(res.data)

↓

React re-renders StatsCard, header status bar, etc.
```

### The WebSocket flow — instant push on trade close

```
Bot closes a trade → calls:
  await state.broadcast_trade({"event": "exit", "pnl": 5.2})

↓

api_server.py sends to all subscribers:
  ws.send_text('{"type":"trade_event","data":{...}}')

↓

RealtimeUpdates.tsx receives it:
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    if (msg.type === 'trade_event') onTradeUpdate()
  }

↓

onTradeUpdate() calls fetchData() → trade list refreshes instantly
```

### The control flow — pause button to bot

```
User clicks "Pause" button in ControlPanel.tsx:
  await axios.post('/api/control/pause')

↓

FastAPI receives POST /api/control/pause:
  self.state.pause_requested = True
  return {"status": "pause_requested"}

↓

Bot's main loop checks each tick:
  if state.pause_requested:
      skip entry logic
```

The bot loop and the API share the same `BotStateManager` object in memory — no database needed for this kind of signaling.

---

### Architecture Summary

```
┌─────────────────────────────────────────────────────┐
│                     Browser                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │StatsCard │  │Positions │  │   ControlPanel   │  │
│  └──────────┘  │  Panel   │  │  (buttons/forms) │  │
│                └──────────┘  └──────────────────┘  │
│  ┌───────────────────────────────────────────────┐  │
│  │         App.tsx  (state + polling)            │  │
│  └───────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────┐  │
│  │    RealtimeUpdates.tsx  (WebSocket client)    │  │
│  └───────────────────────────────────────────────┘  │
└───────────────────┬──────────────────┬──────────────┘
        HTTP (Axios)│                  │WebSocket
┌───────────────────▼──────────────────▼──────────────┐
│                  FastAPI (port 8000)                 │
│  GET /api/stats     GET /api/positions              │
│  GET /api/trades    POST /api/settings              │
│  POST /api/control/{action}    WebSocket /ws        │
└───────────────────────────────┬─────────────────────┘
                                │ shared object in memory
┌───────────────────────────────▼─────────────────────┐
│              BotStateManager                        │
│  current_stats | current_positions | subscribers    │
│  stop_requested | pause_requested | ...             │
└───────────────────────────────┬─────────────────────┘
                                │ reads/writes
┌───────────────────────────────▼─────────────────────┐
│              Bot Loop (trend_bot.py)                │
└─────────────────────────────────────────────────────┘
```

---

## Recommended Learning Path

1. **Week 1** — JSON + Python classes + `async/await` + FastAPI tutorial (official docs at fastapi.tiangolo.com — it's excellent)
2. **Week 2** — HTML + CSS Box Model + Flexbox + Grid (play on codepen.io)
3. **Week 3** — JavaScript: variables, functions, arrays, fetch, async/await
4. **Week 4** — TypeScript basics + interfaces
5. **Week 5** — React: useState, useEffect, props, component composition (react.dev official tutorial)
6. **Week 6** — Tailwind CSS (tailwindcss.com/docs), Axios, Vite
7. **Week 7** — WebSockets: MDN docs + re-read `RealtimeUpdates.tsx` and `api_server.py`

**Best free resources:**
- FastAPI: https://fastapi.tiangolo.com/tutorial/
- React: https://react.dev/learn
- Tailwind: https://tailwindcss.com/docs
- TypeScript: https://www.typescriptlang.org/docs/handbook/intro.html
- MDN (HTML/CSS/JS): https://developer.mozilla.org