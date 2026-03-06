import logging
from agent.state import AgentState
from services.shipment_service import (
    find_by_thread_id,
    find_by_request_id,
    find_latest_by_email,
)
from models.shipment import Shipment
from core.constants import EmailIntent
import random
import string

logger = logging.getLogger(__name__)

def _generate_request_id():
    """Generates a unique request ID like LOGI-123456."""
    suffix = ''.join(random.choices(string.digits, k=6))
    return f"LOGI-{suffix}"


async def generate_reqid(state: AgentState) -> AgentState:
    """
    Node to ensure a shipment record exists and a request_id is assigned.
    Sets the status to NEW or MISSING_INFO depending on the intent.
    """
    thread_id = state.get("conversation_id") # We check by the parent thread link
    request_id = state.get("request_id")
    customer_email = state.get("customer_email")
    intent = state.get("intent")

    # Try to find existing shipment
    shipment = None
    if request_id:
        shipment = await find_by_request_id(request_id)
    elif thread_id:
        shipment = await find_by_thread_id(thread_id)
    
    if not shipment and customer_email:
        shipment = await find_latest_by_email(customer_email)

    if shipment:
        state["request_id"] = shipment.request_id
        logger.info(f"Matched existing shipment: {shipment.request_id}")
    else:
        # Create a new Request ID
        new_id = _generate_request_id()
        state["request_id"] = new_id
        logger.info(f"Generated new request_id: {new_id}")

    # Set status based on intent
    if intent == EmailIntent.NEW_REQUEST:
        state["status"] = "NEW"
    elif intent == EmailIntent.MISSING_INFORMATION:
        state["status"] = "MISSING_INFO"
    
    return state
