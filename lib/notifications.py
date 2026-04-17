"""
Notification system - sends alerts to Discord, Telegram, etc.
Lightweight and async-friendly for Pi Zero 2.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("notifications")


@dataclass
class NotificationEvent:
    """A notification to send."""
    type: str  # "trade_exit", "startup", "error", etc.
    title: str
    message: str
    severity: str = "info"  # "info", "success", "error", "warning"
    pnl: Optional[float] = None
    side: Optional[str] = None
    extra: Optional[dict] = None


class NotificationRouter:
    """Routes notifications to Discord, Telegram, email, etc."""

    def __init__(self):
        self.discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
        self.telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.discord_webhook or (self.telegram_token and self.telegram_chat_id))

    async def send(self, event: NotificationEvent) -> bool:
        """Send notification to all configured channels. Return True if sent."""
        if not self.enabled:
            return False

        tasks = []
        if self.discord_webhook:
            tasks.append(self._send_discord(event))
        if self.telegram_token and self.telegram_chat_id:
            tasks.append(self._send_telegram(event))

        if not tasks:
            return False

        results = await asyncio.gather(*tasks, return_exceptions=True)
        success = any(r is True for r in results)
        if success:
            logger.info(f"Notification sent: {event.title}")
        return success

    async def _send_discord(self, event: NotificationEvent) -> bool:
        """Send to Discord webhook."""
        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp not installed, Discord notifications disabled")
            return False

        # Emoji based on severity
        emoji = {
            "success": "✅",
            "error": "❌",
            "warning": "⚠️",
            "info": "ℹ️",
        }.get(event.severity, "•")

        # Build message
        if event.pnl is not None:
            pnl_str = f"  **PnL:** `{event.pnl:+.2f} USDC`"
        else:
            pnl_str = ""

        if event.side:
            side_str = f"  **Side:** `{event.side.upper()}`"
        else:
            side_str = ""

        embed = {
            "title": f"{emoji} {event.title}",
            "description": event.message,
            "fields": [],
            "color": {
                "success": 0x10B981,  # green
                "error": 0xEF4444,    # red
                "warning": 0xF59E0B,  # amber
                "info": 0x3B82F6,     # blue
            }.get(event.severity, 0x6B7280),
        }

        if event.pnl is not None:
            embed["fields"].append({
                "name": "PnL",
                "value": f"`{event.pnl:+.2f}` USDC",
                "inline": True,
            })

        if event.side:
            embed["fields"].append({
                "name": "Side",
                "value": event.side.upper(),
                "inline": True,
            })

        if event.extra:
            for key, value in event.extra.items():
                embed["fields"].append({
                    "name": key,
                    "value": str(value)[:1024],
                    "inline": True,
                })

        payload = {"embeds": [embed]}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.discord_webhook, json=payload, timeout=5) as resp:
                    return resp.status == 204
        except Exception as e:
            logger.error(f"Discord notification failed: {e}")
            return False

    async def _send_telegram(self, event: NotificationEvent) -> bool:
        """Send to Telegram bot."""
        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp not installed, Telegram notifications disabled")
            return False

        emoji = {
            "success": "✅",
            "error": "❌",
            "warning": "⚠️",
            "info": "ℹ️",
        }.get(event.severity, "•")

        parts = [f"{emoji} <b>{event.title}</b>", event.message]

        if event.pnl is not None:
            parts.append(f"<b>PnL:</b> <code>{event.pnl:+.2f}</code> USDC")

        if event.side:
            parts.append(f"<b>Side:</b> <code>{event.side.upper()}</code>")

        if event.extra:
            for key, value in event.extra.items():
                parts.append(f"<b>{key}:</b> <code>{value}</code>")

        text = "\n".join(parts)
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=5) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")
            return False
