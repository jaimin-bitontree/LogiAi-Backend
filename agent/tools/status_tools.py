"""
agent/tools/status_tools.py

Agentic tools for status operations.
Converted from agent/nodes/status_node.py
"""

import logging
from datetime import datetime
from langchain_core.tools import tool

from config.settings import settings
from config.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import Message
from services.shipment.status_service import get_shipment_status_context
from services.email.email_sender import send_email
from services.email.email_template import build_email
from services.shipment.shipment_service import update_shipment_thread_id, update_shipment, push_message_log

logger = logging.getLogger(__name__)


@tool
async def send_status_update(request_id: str, customer_email: str, customer_name: str = "Customer", last_message_id: str = None) -> str:
    """Send shipment status update to customer.
    
    Args:
        request_id: The shipment request ID (can be empty/null if not provided)
        customer_email: Customer email address
        customer_name: Customer name for personalization
        last_message_id: Last message ID for conversation lookup
        
    Returns:
        Confirmation string with sent message ID
    """
    try:
        logger.info(f"[status_tools] Processing status inquiry for {customer_email}")

        # Check if request_id is missing or invalid
        if not request_id or request_id.lower() in ["null", "none", "", "unknown"]:
            logger.warning(f"[status_tools] No request ID provided by {customer_email}")
            
            # Send email asking for request ID
            request_id_email_html = build_email(
                email_type="missing_info",
                customer_name=customer_name,
                request_id="UNKNOWN",
                missing_fields=["request_id"],
                message=(
                    "We received your status inquiry, but we need your Request ID "
                    "to check your shipment status. Please reply with your Request ID "
                    "(format: REQ-YYYY-XXXXXXXXXXXX) that was provided in your original emails."
                ),
                next_steps=[
                    "Check your previous emails from LogiAI for your Request ID",
                    "Reply to this email with your Request ID",
                    "If you can't find it, forward your original shipment email to us"
                ]
            )
            
            subject = "Request ID Required for Status Inquiry"
            
            msg_id = send_email(
                to=customer_email,
                subject=subject,
                body_html=request_id_email_html,
                request_id="UNKNOWN"
            )
            
            request_id_message_log = Message(
                message_id=msg_id,
                sender_email=settings.GMAIL_ADDRESS,
                sender_type="system",
                direction="outgoing",
                subject=subject,
                body="Request ID required email sent for status inquiry.",
                received_at=datetime.utcnow()
            )

            logger.info(f"[status_tools] Request ID needed email sent to {customer_email}")
            
            return f"✅ Request ID required email sent to {customer_email} | msg_id={msg_id} | status=REQUEST_ID_NEEDED"

        # Continue with normal status lookup using provided request_id
        status_result = await get_shipment_status_context(
            customer_email=customer_email,
            request_id=request_id,
            last_message_id=last_message_id
        )

        if not status_result["found"]:
            logger.warning(f"[status_tools] Shipment {request_id} not found for {customer_email}")
            
            # Enhanced error message with guidance
            guidance_html = build_email(
                email_type="missing_info",
                customer_name=customer_name,
                request_id=request_id,
                missing_fields=[],
                message=(
                    f"We couldn't find a shipment with Request ID: {request_id}. "
                    "Please check your Request ID and try again."
                ),
                next_steps=[
                    "Verify the Request ID format (REQ-YYYY-XXXXXXXXXXXX)",
                    "Check your previous emails from LogiAI",
                    "Contact our support team if you need assistance"
                ]
            )
            
            error_subject = f"Shipment Not Found - {request_id}"
            error_msg_id = send_email(
                to=customer_email,
                subject=error_subject,
                body_html=guidance_html,
                request_id=request_id
            )
            
            # Log error email to database
            error_message_log = Message(
                message_id=error_msg_id,
                sender_email=settings.GMAIL_ADDRESS,
                sender_type="system",
                direction="outgoing",
                subject=error_subject,
                body=f"Status inquiry error: Shipment not found",
                received_at=datetime.utcnow(),
            )
            
            await push_message_log(
                request_id=request_id,
                message=error_message_log.model_dump(),
                sent_message_id=error_msg_id,
                status="NOT_FOUND",
            )

            return f"❌ Shipment {request_id} not found | guidance_email_sent | msg_id={error_msg_id}"

        # Shipment found - proceed with normal status update
        shipment = status_result["shipment"]
        
        # Extract customer name from request_data if available, otherwise use provided name
        extracted_customer_name = (
            shipment.request_data.get("required", {}).get("customer_name") or
            shipment.request_data.get("customer_name") or
            customer_name
        )

        # Prepare status email
        all_fields = REQUIRED_FIELDS + OPTIONAL_FIELDS
        email_body = build_email(
            email_type="status",
            customer_name=extracted_customer_name,
            request_id=shipment.request_id,
            request_data=shipment.request_data,
            all_fields=all_fields,
            status=shipment.status,
            message=f"I have checked our system, and your shipment {shipment.request_id} is currently in {shipment.status.replace('_', ' ')} status."
        )

        # Send status email
        subject = f"Shipment Status Update - {shipment.request_id}"
        outgoing_message_id = send_email(
            to=customer_email,
            subject=subject,
            body_html=email_body,
            request_id=shipment.request_id
        )

        # Prepare outgoing message object
        outgoing_msg = Message(
            message_id=outgoing_message_id,
            sender_email=settings.GMAIL_ADDRESS,
            sender_type="system",
            direction="outgoing",
            subject=subject,
            body="Automated status update reply.",
            received_at=datetime.utcnow()
        )

        # Update database
        await update_shipment_thread_id(
            request_id=shipment.request_id,
            new_thread_id=outgoing_message_id,
            new_message=outgoing_msg.model_dump()
        )
        
        # Also log the message using push_message_log for consistency
        await push_message_log(
            request_id=shipment.request_id,
            message=outgoing_msg.model_dump(),
            sent_message_id=outgoing_message_id,
            status=shipment.status,
        )

        logger.info(f"[status_tools] Status update sent for {shipment.request_id}")
        
        return f"✅ Status update sent to {customer_email} | msg_id={outgoing_message_id} | status={shipment.status}"

    except Exception as e:
        logger.error(f"[status_tools] Error sending status update: {e}")
        return f"❌ Failed to send status update: {str(e)}"


@tool
async def update_shipment_status(request_id: str, new_status: str) -> str:
    """Update shipment status in database.
    
    Args:
        request_id: The shipment request ID
        new_status: New status to set (QUOTED, CONFIRMED, CANCELLED, etc.)
        
    Returns:
        Confirmation string with status update
    """
    try:
        from services.shipment.shipment_service import update_shipment
        
        await update_shipment(request_id, {"status": new_status})
        
        logger.info(f"[status_tools] Updated {request_id} status to {new_status}")
        
        return f"✅ Status updated to {new_status} | request_id={request_id}"

    except Exception as e:
        logger.error(f"[status_tools] Error updating status: {e}")
        return f"❌ Failed to update status: {str(e)}"