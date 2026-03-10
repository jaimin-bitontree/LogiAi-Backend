"""
agent/tools/confirmation_tools.py

Agentic tools for confirmation operations.
Converted from agent/nodes/confirmation_node.py
"""

import logging
from datetime import datetime
from langchain_core.tools import tool

from config import settings
from core.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import Message
from services.email_sender import send_email
from utils.email_template import build_email
from api.shipment_service import update_shipment_data, push_message_log
from db.client import get_db

logger = logging.getLogger(__name__)


@tool
async def process_shipment_confirmation(request_id: str, customer_email: str) -> dict:
    """Process customer shipment confirmation.
    
    Args:
        request_id: The shipment request ID
        customer_email: Customer email address
        
    Returns:
        Result with confirmation status and details
    """
    try:
        logger.info(f"[confirmation_tools] Processing confirmation for {request_id}")

        # Fetch shipment from DB
        db = get_db()
        shipment = await db.shipments.find_one({"request_id": request_id})

        if not shipment:
            return {"success": False, "error": f"Shipment {request_id} not found"}

        current_status = shipment.get("status", "")
        request_data = shipment.get("request_data", {})
        subject = shipment.get("subject") or "Your Shipment"

        logger.info(f"[confirmation_tools] Found shipment | status={current_status}")

        operator_email = settings.OPERATOR_EMAIL
        all_fields = REQUIRED_FIELDS + OPTIONAL_FIELDS
        customer_name = (
            request_data.get("required", {}).get("customer_name") or
            request_data.get("customer_name") or
            "Customer"
        )

        # Handle PRICING_PENDING status
        if current_status == "PRICING_PENDING":
            logger.info(f"[confirmation_tools] Sending pricing reminder to operator")

            reminder_html = build_email(
                email_type="pricing",
                customer_name="Operator",
                request_id=request_id,
                request_data=request_data,
                all_fields=all_fields,
                pricing_details=[],
            )
            reminder_subject = f"[REMINDER] Pricing Required -- {request_id}"

            reminder_msg_id = send_email(
                to=operator_email,
                subject=reminder_subject,
                body_html=reminder_html,
                request_id=request_id
            )

            reminder_log = Message(
                message_id=reminder_msg_id,
                sender_email=settings.GMAIL_ADDRESS,
                sender_type="system",
                direction="outgoing",
                subject=reminder_subject,
                body="Pricing reminder sent to operator.",
                received_at=datetime.utcnow()
            )

            await push_message_log(
                request_id=request_id,
                message=reminder_log.model_dump(),
                sent_message_id=reminder_msg_id,
                status="PRICING_PENDING",
            )

            return {
                "success": True,
                "message": "Pricing reminder sent to operator",
                "status": "PRICING_PENDING",
                "message_id": reminder_msg_id
            }

        # Handle non-QUOTED status
        if current_status != "QUOTED":
            return {
                "success": False,
                "error": f"Cannot confirm shipment with status '{current_status}', expected 'QUOTED'"
            }

        # Process confirmation for QUOTED shipment
        
        # 1. Send notification to operator
        operator_html = build_email(
            email_type="status",
            customer_name="Operator",
            request_id=request_id,
            request_data=request_data,
            all_fields=all_fields,
            status="CONFIRMED",
            message=(
                f"The customer ({customer_name}) has confirmed the shipment. "
                "Please proceed with the logistics arrangements."
            ),
        )
        operator_subject = f"Customer Confirmed Shipment -- {request_id}"

        operator_msg_id = send_email(
            to=operator_email,
            subject=operator_subject,
            body_html=operator_html,
            request_id=request_id
        )

        operator_message_log = Message(
            message_id=operator_msg_id,
            sender_email=settings.GMAIL_ADDRESS,
            sender_type="system",
            direction="outgoing",
            subject=operator_subject,
            body="Operator notified -- customer confirmed the shipment.",
            received_at=datetime.utcnow()
        )

        await push_message_log(
            request_id=request_id,
            message=operator_message_log.model_dump(),
            sent_message_id=operator_msg_id,
            status="CONFIRMED",
        )

        # 2. Update status to CONFIRMED
        await update_shipment_data({
            "request_id": request_id,
            "status": "CONFIRMED",
        })

        # 3. Send thank-you email to customer
        customer_html = build_email(
            email_type="status",
            customer_name=customer_name,
            request_id=request_id,
            request_data=request_data,
            all_fields=all_fields,
            status="CONFIRMED",
            message=(
                "Thank you for confirming your shipment with LogiAI. "
                "We are delighted to have you on board and will handle your shipment "
                "with the utmost care and professionalism."
            ),
            next_steps=[
                "Our team will coordinate all logistics for your shipment",
                "You will receive regular updates on the shipment progress",
                "Feel free to contact us anytime with your Request ID for any queries",
            ]
        )
        customer_subject = f"Re: {subject} -- Shipment Confirmed"

        customer_msg_id = send_email(
            to=customer_email,
            subject=customer_subject,
            body_html=customer_html,
            request_id=request_id
        )

        customer_message_log = Message(
            message_id=customer_msg_id,
            sender_email=settings.GMAIL_ADDRESS,
            sender_type="system",
            direction="outgoing",
            subject=customer_subject,
            body="Thank-you email sent to customer -- shipment confirmed.",
            received_at=datetime.utcnow()
        )

        await push_message_log(
            request_id=request_id,
            message=customer_message_log.model_dump(),
            sent_message_id=customer_msg_id,
            status="CONFIRMED",
        )

        logger.info(f"[confirmation_tools] Confirmation processed for {request_id}")
        
        return {
            "success": True,
            "message": f"Shipment {request_id} confirmed successfully",
            "status": "CONFIRMED",
            "operator_message_id": operator_msg_id,
            "customer_message_id": customer_msg_id
        }

    except Exception as e:
        logger.error(f"[confirmation_tools] Error processing confirmation: {e}")
        return {"success": False, "error": str(e)}