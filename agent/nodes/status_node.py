from agent.state import AgentState
from services.status_service import get_shipment_status_context
import asyncio

async def status_handler(state: AgentState) -> AgentState:
    """
    Handles shipment status inquiries by fetching context from the database.
    """
    customer_email = state.get("customer_email")
    request_id     = state.get("request_id") # Extracted by intent node or provided in email
    thread_id      = state.get("thread_id")
    # For now, we use thread_id which is the current message id or parent id

    print(f"\n[status_handler] Fetching status for {customer_email}")

    status_result = await get_shipment_status_context(
        customer_email=customer_email,
        request_id=request_id,
        thread_id=thread_id
    )

    if status_result["found"]:
        #sent status mail
        #write mail logic here 
        return state
