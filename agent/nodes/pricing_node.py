from datetime import datetime
from agent.state import AgentState
from models.shipment import Message
from services.pricing_service import extract_pricing_data
from services.shipment_service import find_by_request_id
from services.email_sender import send_email
from utils.email_template import build_email
from api.shipment_service import push_message_log
from core.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from config import settings


async def pricing_node(state: AgentState) -> AgentState:
    """
    Handles pricing emails from the operator.
    State already has request_id and shipment data loaded by parse_node.
    
    Steps:
    1. Extract pricing data from email body
    2. Build quote email
    3. Send quote to customer
    4. Update database
    """
    body = state.get("body", "")
    request_id = state.get("request_id", "")
    
    print(f"\n[pricing_handler] Processing operator pricing email for {request_id}...")

    # Validate that we have a request_id from parse_node
    if not request_id:
        print(f"❌ [pricing_handler] No request_id in state.")
        state["status"] = "ERROR"
        return state

    # 1. Extract pricing data from email body
    pricing_data, _ = extract_pricing_data(body)
    if not pricing_data:
        print(f"❌ [pricing_handler] Failed to extract pricing data from email.")
        state["status"] = "ERROR"
        return state

    # 2. Get fresh shipment data from DB (to ensure we have latest)
    shipment = await find_by_request_id(request_id)
    if not shipment:
        print(f"❌ [pricing_handler] Shipment {request_id} not found in database.")
        state["status"] = "ERROR"
        return state

    print(f"✅ [pricing_handler] Found shipment for customer: {shipment.customer_email}")

    customer_email = shipment.customer_email
    customer_name = shipment.request_data.get("required", {}).get("customer_name") or \
                    shipment.request_data.get("customer_name") or \
                    customer_email

    # 3. Build quote email
    all_fields = REQUIRED_FIELDS + OPTIONAL_FIELDS
    email_body = build_email(
        email_type="pricing",
        customer_name=customer_name,
        request_id=request_id,
        pricing=pricing_data,
        request_data=shipment.request_data,
        all_fields=all_fields
    )

    # 4. Send email to customer
    out_subject = f"LogiAI Quotation — {request_id}: {pricing_data.transport_mode or ''}"
    outgoing_message_id = send_email(
        to=customer_email,
        subject=out_subject,
        body_html=email_body,
        request_id=request_id
    )

    # 5. Log interaction
    outgoing_msg = Message(
        message_id=outgoing_message_id,
        sender_email=settings.GMAIL_ADDRESS,
        sender_type="system",
        direction="outgoing",
        subject=out_subject,
        body=f"Quotation sent to customer. Transport Mode: {pricing_data.transport_mode}",
        received_at=datetime.utcnow()
    )

    # 6. Update database
    await push_message_log(
        request_id=request_id,
        message=outgoing_msg.model_dump(),
        sent_message_id=outgoing_message_id,
        status="QUOTED"
    )
    
    # Save pricing details
    from db.client import get_db
    db = get_db()
    await db.shipments.update_one(
        {"request_id": request_id},
        {"$push": {"pricing_details": pricing_data.model_dump()}}
    )

    # 7. Update state
    state["status"] = "QUOTED"
    state["pricing_details"].append(pricing_data)
    state["messages"].append(outgoing_msg)
    state["message_ids"].append(outgoing_message_id)

    print(f"✅ [pricing_handler] Quote sent for {request_id} to {customer_email}")
    return state
