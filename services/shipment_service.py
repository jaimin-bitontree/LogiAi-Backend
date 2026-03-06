from db.client import get_db
from models.shipment import Shipment


async def find_by_thread_id(thread_id: str):
    db = get_db()
    doc = await db.shipments.find_one({"thread_id": thread_id})
    return Shipment(**doc) if doc else None


async def create_shipment(shipment: Shipment):
    db = get_db()
    await db.shipments.insert_one(shipment.dict())