from typing import Optional
from db.client import get_db
from models.shipment import Shipment

async def find_by_thread_id(thread_id: str) -> Optional[Shipment]:
    """Find a shipment by its Gmail thread ID."""
    db = get_db()
    doc = await db.shipments.find_one({"thread_id": thread_id})
    return Shipment(**doc) if doc else None

async def find_by_request_id(request_id: str) -> Optional[Shipment]:
    """Find a shipment by its LogiAI Request ID."""
    db = get_db()
    doc = await db.shipments.find_one({"request_id": request_id})
    return Shipment(**doc) if doc else None

async def find_latest_by_email(customer_email: str) -> Optional[Shipment]:
    """Find the most recent shipment for a given customer email."""
    db = get_db()
    # Sort by created_at descending to get the latest one
    doc = await db.shipments.find_one(
        {"customer_email": customer_email},
        sort=[("created_at", -1)]
    )
    return Shipment(**doc) if doc else None
