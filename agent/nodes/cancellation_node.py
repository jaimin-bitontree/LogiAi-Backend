from datetime import datetime
from agent.state import AgentState
from models.shipment import Message
from services.cancellation_service import verify_cancellation_eligibility
from services.email_sender import send_email
from utils.email_template import build_email
from api.shipment_service import push_message_log
from core.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from config import settings

async def cancellation_handler(state: AgentState) -> AgentState:
    """
    Handles shipment cancellation requests.
    1. Verifies if the shipment can be cancelled.
    2. Updates status to CANCELLED in DB if eligible.
    3. Sends a confirmation (or rejection) email to the user.
    4. Logs the interaction.
    """
    customer_email = state.get("customer_email")
    request_id     = state.get("request_id")
    subject        = state.get("subject") or "Shipment Cancellation Request"

    print(f"\n[cancellation_handler] Processing cancellation for {request_id} from {customer_email}")

    # 1. Verify Eligibility
    verification = await verify_cancellation_eligibility(
        customer_email=customer_email,
        request_id=request_id
    )

    if not verification["eligible"]:
        error_msg = verification["error"]
        print(f"[cancellation_handler] Cancellation rejected: {error_msg}")
        
        # Send Rejection Email
        email_body = build_email(
            email_type="status",
            customer_name=customer_email,
            request_id=request_id or "N/A",
            status="CANCEL_REJECTED",
            message=f"Your cancellation request could not be processed: {error_msg}"
        )
        
        outgoing_message_id = send_email(
            to=customer_email,
            subject=f"Re: {subject} — Cancellation Request",
            body_html=email_body,
            request_id=request_id or ""
        )
        
        # Update state with this interaction
        outgoing_msg = Message(
            message_id=outgoing_message_id,
            sender_email=settings.GMAIL_ADDRESS,
            sender_type="system",
            direction="outgoing",
            subject=f"Re: {subject}",
            body=f"Cancellation rejected: {error_msg}",
            received_at=datetime.utcnow()
        )
        
        state["messages"].append(outgoing_msg)
        state["message_ids"].append(outgoing_message_id)
        return state

    # 2. Process Cancellation
    shipment = verification["shipment"]
    
    # Update Status in DB and maintain log
    all_fields = REQUIRED_FIELDS + OPTIONAL_FIELDS
    email_body = build_email(
        email_type="status",
        customer_name=shipment.request_data.get("customer_name") or customer_email,
        request_id=shipment.request_id,
        request_data=shipment.request_data,
        all_fields=all_fields,
        status="CANCELLED",
        message=f"As per your request, shipment {shipment.request_id} has been successfully cancelled."
    )

    out_subject = f"Re: {subject} — Shipment Cancelled 🛑"
    outgoing_message_id = send_email(
        to=customer_email,
        subject=out_subject,
        body_html=email_body,
        request_id=shipment.request_id
    )

    outgoing_msg = Message(
        message_id=outgoing_message_id,
        sender_email=settings.GMAIL_ADDRESS,
        sender_type="system",
        direction="outgoing",
        subject=out_subject,
        body=f"Shipment {shipment.request_id} cancelled by user.",
        received_at=datetime.utcnow()
    )

    # Persist to DB using push_message_log which sets status and logs message
    await push_message_log(
        request_id=shipment.request_id,
        message=outgoing_msg.model_dump(),
        sent_message_id=outgoing_message_id,
        status="CANCELLED"
    )

    # 3. Update state
    state["status"] = "CANCELLED"
    state["messages"].append(outgoing_msg)
    state["message_ids"].append(outgoing_message_id)
    state["last_message_id"] = outgoing_message_id

    print(f"✅ [cancellation_handler] Shipment {shipment.request_id} cancelled and user notified.")
    return state
