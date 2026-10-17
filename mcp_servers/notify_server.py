"""Notify MCP Server for DispatchMind.

Provides messaging tool sending notifications via Telegram Bot API or
logging to console and store.messages collection in DEMO_MODE or when token is missing.
All operations are resiliently protected.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
import uuid
import httpx

from fastmcp import FastMCP
from core.config import DEMO_MODE, TELEGRAM_BOT_TOKEN
from core.resilience import resilient
from core.store import get_store

logger = logging.getLogger(__name__)

mcp = FastMCP("NotifyServer")


def fallback_send_message(channel: str, chat_id: str, text: str) -> Dict[str, Any]:
    """Fallback notification handler: logs to console and stores in store.messages collection."""
    store = get_store()
    msg_id = f"msg_{uuid.uuid4().hex[:8]}"
    record = {
        "id": msg_id,
        "message_id": msg_id,
        "channel": channel,
        "chat_id": chat_id,
        "text": text,
        "status": "sent",
        "delivery_method": "demo_fallback",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # Save to messages collection
    store.set("messages", msg_id, record)
    logger.info("[NOTIFY FALLBACK] [%s -> %s]: %s", channel, chat_id, text)
    return {
        "status": "sent",
        "channel": channel,
        "chat_id": chat_id,
        "message_id": msg_id,
        "delivery_method": "demo_fallback",
    }


@mcp.tool()
@resilient(fallback=fallback_send_message, retries=2)
def send_message(channel: str, chat_id: str, text: str) -> Dict[str, Any]:
    """Send a notification message to a driver, customer, or dispatcher.

    Args:
        channel: Delivery channel (e.g., 'telegram', 'sms', 'whatsapp', 'internal').
        chat_id: Target recipient chat ID or phone number.
        text: Notification message body.

    Returns:
        Dict with 'status', 'channel', and 'message_id'.
    """
    token = TELEGRAM_BOT_TOKEN
    is_telegram = channel.lower() == "telegram"

    if DEMO_MODE or not token or not is_telegram:
        return fallback_send_message(channel, chat_id, text)

    # Dispatch to Telegram Bot API when configured
    telegram_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(telegram_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                telegram_msg_id = str(data.get("result", {}).get("message_id", uuid.uuid4().hex[:8]))
                store = get_store()
                record = {
                    "id": telegram_msg_id,
                    "message_id": telegram_msg_id,
                    "channel": "telegram",
                    "chat_id": chat_id,
                    "text": text,
                    "status": "sent",
                    "delivery_method": "telegram_api",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                store.set("messages", telegram_msg_id, record)
                return {
                    "status": "sent",
                    "channel": "telegram",
                    "chat_id": chat_id,
                    "message_id": telegram_msg_id,
                    "delivery_method": "telegram_api",
                }
    except Exception as exc:
        logger.warning("Telegram send failed (%s). Using fallback delivery.", exc)

    return fallback_send_message(channel, chat_id, text)


if __name__ == "__main__":
    mcp.run()
