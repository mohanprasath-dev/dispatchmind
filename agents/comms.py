"""Comms Agent for DispatchMind.

Handles multi-channel, multi-lingual dispatch communications:
- Supported languages: English (en), Hindi (hi), Tamil (ta).
- Generates customer ETA updates, driver reassignment notifications, and dispatcher chat replies.
- Short, punchy messages without em dashes. Always includes new ETA when changed.
"""

import json
import logging
from typing import Optional, Dict, Any, List

from core.models import Order
from core.store import store

logger = logging.getLogger(__name__)

# Multi-lingual templates for notifications
TEMPLATES = {
    "eta_update": {
        "en": "DispatchMind Update: Your delivery for order {order_id} is now estimated at {new_eta}. Track your delivery live.",
        "hi": "डिस्पैचमाइंड अपडेट: आपके आर्डर {order_id} की डिलीवरी अब {new_eta} बजे संभावित है।",
        "ta": "டிஸ்பாட்ச்மைண்ட் தகவல்: உங்கள் ஆர்டர் {order_id} டெலிவரி புதிய நேரம் {new_eta} ஆகும்.",
    },
    "driver_reassignment": {
        "en": "Attention {driver_name}: You have {count} updated deliveries assigned to your route. Please review your stop sequence.",
        "hi": "ध्यान दें {driver_name}: आपके रूट में {count} नए आर्डर जोड़े गए हैं। कृपया अपनी सूची देखें।",
        "ta": "கவனத்திற்கு {driver_name}: உங்கள் வழித்தடத்தில் {count} புதிய டெலிவரிகள் ஒதுக்கப்பட்டுள்ளன. சரிபார்க்கவும்.",
    },
    "dispatcher_alert": {
        "en": "Alert: {details}. Recommended action: {action}.",
        "hi": "चेतावनी: {details}. अनुशंसित कार्रवाई: {action}.",
        "ta": "எச்சரிக்கை: {details}. பரிந்துரைக்கப்பட்ட நடவடிக்கை: {action}.",
    },
}


def format_eta_update(order: Order, new_eta: str, language: str = "en") -> str:
    """Format customer notification for updated ETA in English, Hindi, or Tamil."""
    lang = language.lower() if language else "en"
    if lang not in TEMPLATES["eta_update"]:
        lang = "en"
    template = TEMPLATES["eta_update"][lang]
    msg = template.format(order_id=order.id, new_eta=new_eta)
    # Ensure no em dashes
    return msg.replace("—", "-").replace("–", "-")


def format_driver_reassignment(driver_name: str, orders: list, language: str = "en") -> str:
    """Format notification to driver with reassigned orders."""
    lang = language.lower() if language else "en"
    if lang not in TEMPLATES["driver_reassignment"]:
        lang = "en"
    template = TEMPLATES["driver_reassignment"][lang]
    msg = template.format(driver_name=driver_name, count=len(orders))
    return msg.replace("—", "-").replace("–", "-")


def generate_dispatcher_reply(query: str, state_summary: Optional[Dict[str, Any]] = None, language: str = "en") -> str:
    """Generate concise dispatcher response in the requested language."""
    summary = state_summary or {}
    active_vehicles = summary.get("active_vehicles", 0)
    pending_orders = summary.get("pending_orders", 0)
    alerts_count = summary.get("alerts_count", 0)

    q = query.lower()
    lang = language.lower() if language else "en"

    if lang == "hi":
        if "स्थिति" in q or "status" in q or "fleet" in q:
            return f"फ्लीट स्थिति: {active_vehicles} वाहन सक्रिय, {pending_orders} आर्डर लंबित, {alerts_count} सक्रिय अलर्ट।"
        if "alert" in q or "चेतावनी" in q:
            return f"वर्तमान में {alerts_count} चेतावनी सक्रिय हैं। रीकवरी प्रक्रिया जारी है।"
        return f"डिस्पैच अनुरोध प्राप्त हुआ। फ्लीट सुचारू रूप से कार्य कर रही है।"

    elif lang == "ta":
        if "நிலை" in q or "status" in q or "fleet" in q:
            return f"வாகன நிலை: {active_vehicles} வாகனங்கள் இயக்கத்தில் உள்ளன, {pending_orders} ஆர்டர்கள் நிலுவையில் உள்ளன, {alerts_count} எச்சரிக்கைகள் உள்ளன."
        if "alert" in q or "எச்சரிக்கை" in q:
            return f"தற்போது {alerts_count} எச்சரிக்கைகள் உள்ளன. மீட்பு நடவடிக்கை எடுக்கப்பட்டு வருகிறது."
        return f"உங்கள் கோரிக்கை பெறப்பட்டது. வாகனங்கள் இயக்கத்தில் உள்ளன."

    # Default English
    if "status" in q or "fleet" in q or "overview" in q:
        return f"Fleet status: {active_vehicles} active vehicles, {pending_orders} pending orders, {alerts_count} active alerts."
    if "alert" in q or "delay" in q:
        return f"Currently tracking {alerts_count} operational alerts. Auto-recovery is active."
    return f"DispatchMind ready. All operational metrics updated across routes."


def build_agent():
    """Build and export Google ADK Comms Agent."""
    from google.adk.agents import Agent

    def comms_eta_tool(order_id: str, new_eta: str, language: str = "en") -> str:
        """Format an ETA update notification in English, Hindi, or Tamil."""
        raw_order = store.get("orders", order_id)
        if raw_order:
            order = Order(**raw_order) if isinstance(raw_order, dict) else raw_order
        else:
            order = Order(
                id=order_id,
                customer_name="Valued Customer",
                phone="9840112233",
                address="Chennai",
                pincode="600001",
                weight_kg=10.0,
            )
        return format_eta_update(order, new_eta, language)

    agent = Agent(
        name="comms",
        model="gemini-2.5-flash",
        description="Multi-lingual dispatch communications agent for drivers, customers, and dispatchers.",
        instruction=(
            "You are the Comms Agent for DispatchMind. "
            "Communicate clearly and concisely in English, Hindi, or Tamil. "
            "Never use em dashes in any messages. "
            "Always include updated ETAs whenever route timings change."
        ),
        tools=[comms_eta_tool],
    )
    return agent
