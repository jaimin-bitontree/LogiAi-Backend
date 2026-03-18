from fastapi import APIRouter, HTTPException, Query
from services.shipment.shipment_service import find_by_request_id, find_by_thread_id, list_shipments
from services.notification.notification_service import send_quote_notification
from models.shipment import Shipment
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shipments", tags=["shipments"])

@router.get("/", response_model=List[Shipment])
async def get_all_shipments(
    status: Optional[str] = Query(None, description="Filter by shipment status")
):
    """
    Get all shipments with optional status filtering.
    Returns all matching shipments without pagination.
    """
    return await list_shipments(status=status)

@router.get("/{request_id}", response_model=Shipment)
async def get_shipment_by_id(request_id: str):
    """
    Retrieve shipment details by its LogiAI Request ID.
    Example: LOGI-123456
    """
    shipment = await find_by_request_id(request_id)
    if not shipment:
        raise HTTPException(status_code=404, detail=f"Shipment with ID {request_id} not found")
    return shipment

@router.get("/thread/{thread_id}", response_model=Shipment)
async def get_shipment_by_thread_id(thread_id: str):
    """
    Retrieve shipment details by its Gmail Thread ID.
    """
    shipment = await find_by_thread_id(thread_id)
    if not shipment:
        raise HTTPException(status_code=404, detail=f"Shipment with Thread ID {thread_id} not found")
    return shipment


@router.post("/{request_id}/notify")
async def send_notification(request_id: str):
    """Send notification email for a quoted shipment"""
    try:
        # Find shipment by request_id
        shipment = await find_by_request_id(request_id)
        if not shipment:
            raise HTTPException(status_code=404, detail="Shipment not found")
        
        # Check if status is QUOTED
        if shipment.status != "QUOTED":
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot send notification. Shipment status is {shipment.status}, expected QUOTED"
            )
        
        # Send notification
        result = await send_quote_notification(request_id)
        
        return {
            "success": True,
            "message": "Notification sent successfully",
            "request_id": request_id,
            "message_id": result["message_id"],
            "customer_email": result["customer_email"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending notification for {request_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to send notification")
