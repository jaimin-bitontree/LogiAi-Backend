from fastapi import APIRouter, HTTPException
from models.shipment import Shipment, Message
from services.shipment_service import create_shipment, find_by_thread_id
from schemas.shipment_schema import (
    StoreStateRequest,
    StoreStateResponse,
    ShipmentStateResponse,
)

router = APIRouter(prefix="/shipments", tags=["Shipments"])


@router.get("/by-thread/{thread_id}", response_model=ShipmentStateResponse)
async def get_by_thread_id(thread_id: str):
    """Fetch an existing shipment by thread_id. Called by the reqid node to hydrate state."""
    shipment = await find_by_thread_id(thread_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return ShipmentStateResponse(
        request_id=shipment.request_id,
        thread_id=shipment.thread_id,
        last_message_id=shipment.last_message_id,
        status=shipment.status,
        intent=shipment.intent,
        message_ids=shipment.message_ids,
        attachments=shipment.attachments,
    )


@router.post("/store", response_model=StoreStateResponse, status_code=201)
async def store_state(payload: StoreStateRequest):
    """Receive agent state after reqid node and persist it as a Shipment in DB."""
    message = Message(
        message_id=payload.message_ids[0] if payload.message_ids else "",
        sender_email=payload.customer_email,
        sender_type="customer",
        direction="incoming",
        subject=payload.subject,
        body=payload.body,
        attachments=payload.attachments or [],
    )
    shipment = Shipment(
        request_id=payload.request_id,
        thread_id=payload.thread_id,
        customer_email=payload.customer_email,
        subject=payload.subject,
        body=payload.body,
        attachments=payload.attachments or [],
        messages=[message],
        message_ids=payload.message_ids or [],
        last_message_id=payload.last_message_id,
        translated_body=payload.translated_body,
        translated_subject=payload.translated_subject,
        language_metadata=payload.language_metadata,
    )
    await create_shipment(shipment)
    return StoreStateResponse(request_id=payload.request_id, status="NEW")
