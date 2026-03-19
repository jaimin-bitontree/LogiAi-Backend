"""
agent/tools/confirmation_tools.py

Agentic tools for confirmation operations.
Converted from agent/nodes/confirmation_node.py
"""

import logging
from datetime import datetime
from langchain_core.tools import tool

from config.settings import settings
from config.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import Message
from services.email.email_sender import send_email
from services.email.email_template import build_email
from services.shipment.shipment_service import update_shipment, find_by_request_id, find_by_any_message_id, log_outgoing_message , push_message_log
from services.ai.language_service import translate_to_language, translate_text_to_language
from utils.language_helpers import get_detected_lang

logger = logging.getLogger(__name__)


@tool
async def process_shipment_confirmation(request_id: str, customer_email: str, customer_name: str = "Customer", conversation_id: str = None) -> str:
    """Process customer shipment confirmation.
    
    Args:
        request_id: The shipment request ID (can be empty/null if not provided)
        customer_email: Customer email address
        customer_name: Customer name for personalization
        conversation_id: The In-Reply-To header (None if new email, not a reply)
        
    Returns:
        Confirmation string with sent message IDs
    """
    try:
        logger.info(f"[confirmation_tools] Processing confirmation for {request_id}")
        
        # 1. Fetch shipment from DB immediately if either ID is provided
        shipment = None
        if request_id and request_id.lower() not in ["null", "none", "", "unknown"]:
            shipment = await find_by_request_id(request_id)
            logger.info(f"[confirmation_tools] Found by request_id: {request_id}")
        elif conversation_id and conversation_id.lower() not in ["null", "none", "", "unknown"]:
            shipment = await find_by_any_message_id(conversation_id)
            if shipment:
                request_id = shipment.request_id  # Update request_id
                logger.info(f"[confirmation_tools] Found by conversation_id: {request_id}")

        # 2. Get detected_lang securely
        detected_lang = get_detected_lang(shipment) if shipment else "en"

        # 3. Handle missing shipment scenario
        if not shipment:
            # Check if we didn't even have IDs to begin with
            if (not request_id or request_id.lower() in ["null", "none", "", "unknown"]) and \
               (not conversation_id or conversation_id.lower() in ["null", "none", "", "unknown"]):
                logger.warning(f"[confirmation_tools] No request ID provided by {customer_email}")
                
                request_id_email_html = build_email(
                    email_type="missing_info",
                    customer_name=customer_name,
                    request_id="UNKNOWN",
                    missing_fields=["request_id"],
                    message=(
                        "We received your confirmation request, but we need your Request ID "
                        "to process it. Please reply with your Request ID (format: REQ-YYYY-XXXXXXXXXXXX) "
                        "that was provided in your original pricing email."
                    ),
                    next_steps=[
                        "Check your previous emails from LogiAI for your Request ID",
                        "Reply to this email with your Request ID",
                        "If you can't find it, forward your original pricing email to us"
                    ]
                )
                
                subject = "Request ID Required for Shipment Confirmation"
                
                msg_id = send_email(
                    to=customer_email,
                    subject=subject,
                    body_html=request_id_email_html,
                    request_id="UNKNOWN"
                )
                
                logger.info(f"[confirmation_tools] Request ID needed email sent to {customer_email}")
                return f"✅ Request ID required email sent to {customer_email} | msg_id={msg_id} | status=REQUEST_ID_NEEDED"

            else:
                # We had an ID, but shipment not found
                logger.warning(f"[confirmation_tools] Shipment {request_id} not found")
                
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
                
                return f"❌ Shipment {request_id} not found | guidance_email_sent | msg_id={error_msg_id}"

        current_status = shipment.status or ""
        request_data = shipment.request_data or {}
        subject = shipment.subject or "Your Shipment"

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

            return f"✅ Pricing reminder sent to operator | msg_id={reminder_msg_id} | status=PRICING_PENDING"

        # Handle non-QUOTED status
        # if current_status != "QUOTED":
        #     return f"❌ Cannot confirm shipment with status '{current_status}', expected 'QUOTED'"

        if current_status == "CONFIRMED":
            already_confirmed_html = build_email(
                email_type="status",
                customer_name=customer_name,
                request_id=request_id,
                request_data=request_data,
                all_fields=all_fields,
                status="CONFIRMED",
                message="Your shipment is already confirmed and currently in process. Our team is handling your logistics arrangements.",
            )
            already_subject = f"Shipment Already Confirmed - {request_id}"
 
            if detected_lang != "en":
                already_confirmed_html = translate_to_language(already_confirmed_html, detected_lang)
                already_subject = translate_text_to_language(already_subject, detected_lang)
 
            msg_id = send_email(to=customer_email, subject=already_subject, body_html=already_confirmed_html, request_id=request_id)
            await log_outgoing_message(request_id=request_id, message_id=msg_id, subject=already_subject, body="Already confirmed email sent to customer.", status="CONFIRMED")
            return f"✅ Already confirmed email sent to {customer_email} | msg_id={msg_id} | status=CONFIRMED"
 
# Handle any other non-QUOTED status
        if current_status != "QUOTED":
            not_quoted_html = build_email(
                email_type="status",
                customer_name=customer_name,
                request_id=request_id,
                request_data=request_data,
                all_fields=all_fields,
                status=current_status,
                message="Confirmation is only allowed after a quotation has been sent. Please wait until you receive a pricing quote before confirming.",
            )
            not_quoted_subject = f"Confirmation Not Available Yet - {request_id}"
 
            if detected_lang != "en":
                not_quoted_html = translate_to_language(not_quoted_html, detected_lang)
                not_quoted_subject = translate_text_to_language(not_quoted_subject, detected_lang)
 
            msg_id = send_email(to=customer_email, subject=not_quoted_subject, body_html=not_quoted_html, request_id=request_id)
            await log_outgoing_message(request_id=request_id, message_id=msg_id, subject=not_quoted_subject, body="Confirmation not available — quotation not yet sent.", status=current_status)
            return f"✅ Not-quoted email sent to {customer_email} | msg_id={msg_id} | status={current_status}"

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
        await update_shipment(request_id, {
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

        # Language translation for customer confirmation email
        if detected_lang != "en":
            logger.info(f"[confirmation_tools] Translating confirmation email to '{detected_lang}' for {customer_email}")
            customer_html = translate_to_language(customer_html, detected_lang)
            customer_subject = translate_text_to_language(customer_subject, detected_lang)

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
        
        return f"✅ Confirmation email sent to {customer_email} | operator_msg_id={operator_msg_id} | customer_msg_id={customer_msg_id} | status=CONFIRMED"

    except Exception as e:
        logger.error(f"[confirmation_tools] Error processing confirmation: {e}")
        return f"❌ Failed to process confirmation: {str(e)}"