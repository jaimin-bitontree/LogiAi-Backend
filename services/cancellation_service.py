from typing import Dict, Any, Optional
from services.shipment_service import find_by_request_id

async def verify_cancellation_eligibility(
    customer_email: str,
    request_id: str
) -> Dict[str, Any]:
    """
    Verifies if a shipment can be cancelled by the requester.
    """
    if not request_id:
        return {"eligible": False, "error": "No Request ID provided."}

    shipment = await find_by_request_id(request_id)

    if not shipment:
        return {"eligible": False, "error": f"Shipment {request_id} not found."}

    # Security: Email must match
    if shipment.customer_email.lower() != customer_email.lower():
        return {
            "eligible": False, 
            "error": "You do not have permission to cancel this shipment."
        }

    # Status check
    if shipment.status == "CANCELLED":
        return {"eligible": False, "error": f"Shipment {request_id} is already cancelled."}
    
    if shipment.status == "CLOSED":
        return {"eligible": False, "error": f"Shipment {request_id} is already closed and cannot be cancelled."}

    return {
        "eligible": True,
        "shipment": shipment
    }
