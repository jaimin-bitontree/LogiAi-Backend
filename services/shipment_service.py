from datetime import datetime
from db.client import get_db
from models.shipment import Shipment

# Statuses that mean a shipment is still active / awaiting a reply
OPEN_STATUSES = ["MISSING_INFO", "PRICING_PENDING", "QUOTED"]


async def find_by_thread_id(thread_id: str):
    db = get_db()
    doc = await db.shipments.find_one({"thread_id": thread_id})
    return Shipment(**doc) if doc else None


async def create_shipment(shipment: Shipment):
    db = get_db()
    await db.shipments.insert_one(shipment.dict())


async def message_id_already_processed(message_id: str) -> bool:
    """Return True if this Gmail Message-ID is already stored in any shipment."""
    db = get_db()
    doc = await db.shipments.find_one({"message_ids": message_id})
    return doc is not None


async def find_by_last_message_id(last_message_id: str):
    """Lookup shipment by last_message_id field."""
    db = get_db()
    doc = await db.shipments.find_one({"last_message_id": last_message_id})
    return Shipment(**doc) if doc else None


async def find_by_request_id(request_id: str):
    """Lookup shipment by request_id field."""
    db = get_db()
    doc = await db.shipments.find_one({"request_id": request_id})
    return Shipment(**doc) if doc else None


async def find_by_email_and_open_status(customer_email: str):
    """Find the most recent open shipment for a customer email.
    Open means status is one of MISSING_INFO, PRICING_PENDING, or QUOTED.
    """
    db = get_db()
    doc = await db.shipments.find_one(
        {"customer_email": customer_email, "status": {"$in": OPEN_STATUSES}},
        sort=[("created_at", -1)],
    )
    return Shipment(**doc) if doc else None


async def update_shipment_thread_id(request_id: str, new_thread_id: str, attachments: List = None, new_message: dict = None):
    """Update shipment by adding a new message_id, updating thread pointers, appending attachments and messages."""
    db = get_db()
    update_ops = {
        "$addToSet": {"message_ids": new_thread_id},
        "$set": {
            "thread_id": new_thread_id,
            "last_message_id": new_thread_id,
            "updated_at": datetime.utcnow()
        },
    }

    if attachments:
        # Convert Pydantic models to dict if they aren't already
        attachment_dicts = [a.dict() if hasattr(a, "dict") else a for a in attachments]
        update_ops["$push"] = {"attachments": {"$each": attachment_dicts}}
    
    if new_message:
        if "$push" not in update_ops:
            update_ops["$push"] = {}
        update_ops["$push"]["messages"] = new_message

    await db.shipments.update_one({"request_id": request_id}, update_ops)

