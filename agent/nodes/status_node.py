from datetime import datetime
from agent.state import AgentState
from models.shipment import Message
from services.status_service import get_shipment_status_context
from services.email_sender import send_email
from utils.email_template import build_email
from services.shipment_service import update_shipment_thread_id
from core.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
import asyncio
from config import settings

async def status_handler(state: AgentState) -> AgentState:
    """
    Handles shipment status inquiries.
    1. Looks up shipment in DB.
    2. Sends an automated email reply with the current status and extracted details.
    3. Updates the shipment conversation history in the database and state.
    """
    customer_email = state.get("customer_email")
    request_id     = state.get("request_id")
    last_message_id = state.get("conversation_id")  # Get from state instead of thread_id

    print(f"\n[status_handler] Processing status inquiry for {customer_email}")

    status_result = await get_shipment_status_context(
        customer_email=customer_email,
        request_id=request_id,
        last_message_id=conversation_id  # Use conversation_id as last_message_id
    )

    if not status_result["found"]:
        error_msg = status_result.get("error", "Shipment not found or unauthorized.")
        print(f"[status_handler] {error_msg} for {customer_email}")
        
        # Prepare Error Email Content
        email_body = build_email(
            email_type="status",
            customer_name=customer_email,
            request_id=request_id or "N/A",
            status="NOT_FOUND",
            message=f"{error_msg} If you want to know status please give me real request id."
        )

        subject = f"Re: {state.get('subject') or 'Shipment Status Inquiry'}"
        outgoing_message_id = send_email(
            to=customer_email,
            subject=subject,
            body_html=email_body,
            request_id=request_id or ""
        )

        outgoing_msg = Message(
            message_id=outgoing_message_id,
            sender_email=settings.SYSTEM_EMAIL,
            sender_type="system",
            direction="outgoing",
            subject=subject,
            body=f"Status inquiry failed: {error_msg}",
            received_at=datetime.utcnow()
        )

        state["messages"].append(outgoing_msg)
        state["message_ids"].append(outgoing_message_id)
        return state

    shipment = status_result["shipment"]
    
    # Extract customer name from request_data if available
    customer_name = shipment.request_data.get("required", {}).get("customer_name") or \
                    shipment.request_data.get("customer_name") or \
                    customer_email

    # Prepare Email Content
    all_fields = REQUIRED_FIELDS + OPTIONAL_FIELDS
    email_body = build_email(
        email_type="status",
        customer_name=customer_name,
        request_id=shipment.request_id,
        request_data=shipment.request_data,
        all_fields=all_fields,
        status=shipment.status,
        message=f"I have checked our system, and your shipment {shipment.request_id} is currently in {shipment.status.replace('_', ' ')} status."
    )

    # Send Email Reply
    subject = f"Re: {state.get('subject') or 'Shipment Status Update'}"
    outgoing_message_id = send_email(
        to=customer_email,
        subject=subject,
        body_html=email_body,
        request_id=shipment.request_id
    )

    # Prepare outgoing message object
    outgoing_msg = Message(
        message_id=outgoing_message_id,
        sender_email=settings.SYSTEM_EMAIL,
        sender_type="system",
        direction="outgoing",
        subject=subject,
        body="Automated status update reply.",
        received_at=datetime.utcnow()
    )

    # Update State
    if "messages" not in state:
        state["messages"] = []
    state["messages"].append(outgoing_msg)
    
    if "message_ids" not in state:
        state["message_ids"] = []
    state["message_ids"].append(outgoing_message_id)
    


    # Persist to DB
    await update_shipment_thread_id(
        request_id=shipment.request_id,
        new_thread_id=outgoing_message_id,
        new_message=outgoing_msg.model_dump()
    )

    print(f"✅ [status_handler] Status update sent and persisted for {shipment.request_id}")
    return state
