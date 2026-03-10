from fastapi import APIRouter, HTTPException, Query
from services.shipment_service import find_by_request_id, find_by_thread_id, list_shipments
from models.shipment import Shipment
from typing import List, Optional

router = APIRouter(prefix="/shipments", tags=["shipments"])

@router.get("/", response_model=List[Shipment])
async def get_all_shipments(
    status: Optional[str] = Query(None, description="Filter by shipment status"),
    page: int = Query(1, ge=1, description="Page number (starting from 1)"),
    page_size: int = Query(10, ge=1, le=10, description="Items per page (max 10)")
):
    """
    Get a paginated list of shipments.
    You can filter by 'status' and control results per page.
    """
    return await list_shipments(
        status=status, 
        page=page, 
        page_size=page_size
    )

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
