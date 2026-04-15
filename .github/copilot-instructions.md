# Polymarket Trading Bot Repo Instructions

## Project Purpose

This repository contains a Polymarket trading bot focused on short-duration coin direction markets, with both a general trading client layer and a higher-level automated trend-following bot.

## Key Entry Points

- `apps/trend_bot.py`: main automated strategy runner for BTC trend-following, with `--paper` and live modes.
- `scripts/setup.py`: initial setup flow that encrypts the private key and creates `config.yaml`.

## Architecture

- `src/`: core API, signing, config, HTTP, websocket, and trading client logic.
- `lib/`: higher-level runtime components for automation, including market rotation, BTC feed, price tracking, positions, display, and stats.
- `apps/`: strategy applications that compose the lower-level modules into runnable bots.
- `credentials/`: encrypted key material and related local secrets.

## Order Flow Map

- Market data enters through `lib/market_manager.py`, which maintains the active market and orderbook snapshots.
- `apps/trend_bot.py` records those prices into `lib/price_tracker.py` and calls `TrendFollowingStrategy.evaluate()` to produce a `Signal`.
- `AutoBot._tick()` applies entry guards such as cooldown, spread, position capacity, price-band safety, and market-expiry checks before allowing execution.
- `AutoBot._enter()` converts the signal into an order intent by selecting the side, current ask price, token id, and size in shares.
- In paper mode, the bot opens a simulated position through `lib/position_manager.py` without submitting an exchange order.
- In live mode, `AutoBot._enter()` calls `TradingBot.place_order()` in `src/bot.py`.
- `TradingBot.place_order()` builds an `Order`, signs it with `src/signer.py`, and submits it through the CLOB client in `src/client.py`.
- After submission succeeds, the returned order id is attached to the local position state in `lib/position_manager.py` and the trade is logged to `trade_log.jsonl`.
- Exit handling currently closes positions locally from `AutoBot._exit_position()` based on `PositionManager.check_all_exits()`; live sell execution is still marked as TODO and should be treated as incomplete.

## Runtime Model

- Prefer `apps/trend_bot.py` when working on automated strategy behavior.
- Treat paper mode and live mode as materially different execution paths and review both when changing entry, exit, sizing, or order placement logic.
- Live mode requires `POLY_PRIVATE_KEY` and `POLY_SAFE_ADDRESS` from environment variables for `apps/trend_bot.py`.
- The broader client stack also supports encrypted key and `config.yaml` flows used by `scripts/setup.py`.
- Optional Builder credentials enable gasless trading through the relayer path.

## Trading-Specific Guidance

- Prioritize correctness and safety over feature breadth.
- When changing strategy logic, check for effects on cooldowns, spreads, market expiry guards, position limits, and paper/live divergence.
- When changing position logic, verify PnL calculation, take-profit or stop-loss semantics, and any trailing-stop behavior.
- When changing market handling, preserve market-rotation safety and websocket reconnect behavior.
- Avoid making assumptions about real-money order execution unless verified in the existing `TradingBot` and client code.

## Working Style For This Repo

- Keep edits minimal and localized.
- Preserve the existing module split instead of collapsing logic into one file.
- Prefer reading the relevant entrypoint and directly connected modules instead of scanning the whole repository.
- If a change affects trading behavior, call out live-trading risk and whether only paper mode was validated.

## Common Commands

- Install dependencies: `pip install -r requirements.txt`
- Setup credentials and config: `python scripts/setup.py`
- Run automated trend bot in paper mode: `python apps/trend_bot.py --paper`