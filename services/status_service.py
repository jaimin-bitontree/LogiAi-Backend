import logging
from typing import Dict, Any, Optional
from services.shipment_service import (
    find_by_request_id,
    find_by_thread_id,
    find_latest_by_email
)

logger = logging.getLogger(__name__)

async def get_shipment_status_context(
    customer_email: str,
    request_id: Optional[str] = None,
    thread_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Looks up shipment status based on provided IDs and verifies ownership.
    
    Priority:
    1. request_id (explicit tracking)
    2. thread_id (reply context)
    3. customer_email (fallback to latest)
    """
    shipment = None

    # 1. Search by Request ID
    if request_id:
        shipment = await find_by_request_id(request_id)
        if not shipment:
            logger.info(f"Shipment not found for Request ID: {request_id}")

    # 2. Search by Thread ID
    if not shipment and thread_id:
        shipment = await find_by_thread_id(thread_id)
        if not shipment:
            logger.info(f"Shipment not found for Thread ID: {thread_id}")

    # 3. Search by Email (Fallback)
    if not shipment and customer_email:
        shipment = await find_latest_by_email(customer_email)
        if not shipment:
            logger.info(f"No previous shipments found for email: {customer_email}")

    if not shipment:
        return {
            "found": False,
            "error": "No shipment matching your criteria was found."
        }

    # Security Verification: Ensure the requester actually owns the shipment
    if shipment.customer_email.lower() != customer_email.lower():
        logger.warning(
            f"Security Alert: Unauthorized status inquiry for {shipment.request_id} "
            f"from {customer_email} (Owner: {shipment.customer_email})"
        )
        return {
            "found": False,
            "error": "You do not have permission to access this shipment status."
        }

    return {
        "found": True,
        "request_id": shipment.request_id,
        "status": shipment.status,
        "subject": shipment.subject,
        "updated_at": shipment.updated_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(shipment, 'updated_at') else "N/A"
    }
