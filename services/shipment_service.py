from typing import Optional, List
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

async def list_shipments(
    status: Optional[str] = None, 
    page: int = 1, 
    page_size: int = 10
) -> List[Shipment]:
    """
    Fetch shipments with optional status filtering and pagination.
    Ordered by creation date (newest first).
    """
    db = get_db()
    query = {}
    
    if status:
        query["status"] = status
        
    # Calculate how many records to skip
    skip = (page - 1) * page_size
    
    cursor = db.shipments.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    docs = await cursor.to_list(length=page_size)
    
    return [Shipment(**doc) for doc in docs]
