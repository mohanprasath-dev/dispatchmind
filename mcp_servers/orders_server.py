"""Orders MCP Server for DispatchMind.

Provides tool access to orders, vehicles, and audit/event logging backed by the core store.
All operations are resiliently wrapped for robust dispatch operations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastmcp import FastMCP
from core.models import Event, Order, Vehicle
from core.resilience import resilient
from core.store import get_store

mcp = FastMCP("OrdersServer")


@mcp.tool()
@resilient(retries=2)
def list_orders(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List orders from the store with optional status filtering.

    Args:
        status: Optional status string (e.g., 'pending', 'assigned', 'delivered')

    Returns:
        List of order dictionaries.
    """
    store = get_store()
    filters = {"status": status} if status else None
    return store.list("orders", filters=filters)


@mcp.tool()
@resilient(retries=2)
def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve an order by ID.

    Args:
        order_id: The unique order identifier.

    Returns:
        Order dictionary or None if not found.
    """
    store = get_store()
    return store.get("orders", order_id)


@mcp.tool()
@resilient(retries=2)
def create_order(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new delivery order.

    Args:
        order_data: Dictionary containing order attributes.

    Returns:
        The created Order dictionary.
    """
    store = get_store()
    if not order_data.get("id"):
        order_data["id"] = f"ORD-{uuid.uuid4().hex[:6].upper()}"
    if not order_data.get("created_at"):
        order_data["created_at"] = datetime.now(timezone.utc).isoformat()

    order = Order(**order_data)
    store.set("orders", order.id, order)
    return order.model_dump()


@mcp.tool()
@resilient(retries=2)
def update_order(order_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Partially update an existing order.

    Args:
        order_id: Unique order identifier.
        updates: Key-value pairs to update on the order.

    Returns:
        The updated Order dictionary.
    """
    store = get_store()
    existing = store.get("orders", order_id)
    if not existing:
        raise ValueError(f"Order {order_id} not found")

    existing.update(updates)
    order = Order(**existing)
    store.set("orders", order_id, order)
    return order.model_dump()


@mcp.tool()
@resilient(retries=2)
def assign_order(order_id: str, vehicle_id: str) -> Dict[str, Any]:
    """Assign an order to a vehicle and set its status to assigned.

    Args:
        order_id: Unique order identifier.
        vehicle_id: Vehicle identifier.

    Returns:
        The updated Order dictionary.
    """
    store = get_store()
    existing = store.get("orders", order_id)
    if not existing:
        raise ValueError(f"Order {order_id} not found")

    existing["assigned_vehicle"] = vehicle_id
    existing["status"] = "assigned"
    order = Order(**existing)
    store.set("orders", order_id, order)
    return order.model_dump()


@mcp.tool()
@resilient(retries=2)
def list_vehicles() -> List[Dict[str, Any]]:
    """List all fleet vehicles.

    Returns:
        List of vehicle dictionaries.
    """
    store = get_store()
    return store.list("vehicles")


@mcp.tool()
@resilient(retries=2)
def log_event(
    source: str,
    event_type: str,
    status: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Log an operational event or audit entry into the store.

    Args:
        source: Component or agent generating the event.
        event_type: Category of event (e.g., 'dispatch', 'alert', 'recovery').
        status: Status code (e.g., 'info', 'success', 'warning', 'error').
        message: Human-readable message.
        metadata: Optional dictionary with extra context.

    Returns:
        The logged Event dictionary.
    """
    store = get_store()
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    meta = metadata or {}
    event = Event(
        event_id=event_id,
        event_type=event_type,
        source=source,
        status=status,
        message=message,
        reason=meta.get("reason", event_type),
        severity=meta.get("severity", "medium"),
        details=meta,
        metadata=meta,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    store.set("events", event_id, event)
    return event.model_dump()


if __name__ == "__main__":
    mcp.run()
