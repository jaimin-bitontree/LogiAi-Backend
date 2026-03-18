"""
agent/tools/confirmation_tools.py
"""

import logging
from datetime import datetime
from langchain_core.tools import tool

from config.settings import settings
from config.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import Message
from services.email.email_sender import send_email
from services.email.email_template import build_email
from services.shipment.shipment_service import update_shipment, push_message_log, get_shipment_by_request_id
from services.ai.language_service import translate_to_language, translate_text_to_language

logger = logging.getLogger(__name__)


@tool
async def process_shipment_confirmation(
    request_id:     str,
    customer_email: str,
    customer_name:  str = "Customer",
    detected_lang:  str = "en",
) -> str:
    """Process customer shipment confirmation.

    Args:
        request_id: The shipment request ID (can be empty/null if not provided)
        customer_email: Customer email address
        customer_name: Customer name for personalization
        detected_lang: ISO 639-1 language code from DETECTED_LANG in context (e.g. 'fr', 'de')

    Returns:
        Confirmation string with sent message IDs
    """
    try:
        logger.info(f"[confirmation_tools] Processing confirmation for {request_id}")

        # ── No request ID ──────────────────────────────────────────
        if not request_id or request_id.lower() in ["null", "none", "", "unknown"]:
            logger.warning(f"[confirmation_tools] No request ID provided by {customer_email}")

            html    = build_email(
                email_type    = "missing_info",
                customer_name = customer_name,
                request_id    = "UNKNOWN",
                missing_fields= ["request_id"],
                message       = (
                    "We received your confirmation request, but we need your Request ID "
                    "to process it. Please reply with your Request ID (format: REQ-YYYY-XXXXXXXXXXXX) "
                    "that was provided in your original pricing email."
                ),
                next_steps    = [
                    "Check your previous emails from LogiAI for your Request ID",
                    "Reply to this email with your Request ID",
                    "If you can't find it, forward your original pricing email to us",
                ]
            )
            subject = "Request ID Required for Shipment Confirmation"
            if detected_lang != "en":
                html    = translate_to_language(html, detected_lang)
                subject = translate_text_to_language(subject, detected_lang)

            msg_id = send_email(to=customer_email, subject=subject, body_html=html, request_id="UNKNOWN")
            logger.info(f"[confirmation_tools] Request ID needed email sent to {customer_email}")
            return f"✅ Request ID required email sent to {customer_email} | msg_id={msg_id} | status=REQUEST_ID_NEEDED"

        # ── Fetch shipment ─────────────────────────────────────────
        shipment = await get_shipment_by_request_id(request_id)

        if not shipment:
            logger.warning(f"[confirmation_tools] Shipment {request_id} not found")

            html          = build_email(
                email_type    = "missing_info",
                customer_name = customer_name,
                request_id    = request_id,
                missing_fields= [],
                message       = (
                    f"We couldn't find a shipment with Request ID: {request_id}. "
                    "Please check your Request ID and try again."
                ),
                next_steps    = [
                    "Verify the Request ID format (REQ-YYYY-XXXXXXXXXXXX)",
                    "Check your previous emails from LogiAI",
                    "Contact our support team if you need assistance",
                ]
            )
            error_subject = f"Shipment Not Found - {request_id}"
            if detected_lang != "en":
                html          = translate_to_language(html, detected_lang)
                error_subject = translate_text_to_language(error_subject, detected_lang)

            error_msg_id = send_email(to=customer_email, subject=error_subject, body_html=html, request_id=request_id)
            return f"❌ Shipment {request_id} not found | guidance_email_sent | msg_id={error_msg_id}"

        current_status = shipment.get("status", "")
        request_data   = shipment.get("request_data", {})
        subject        = shipment.get("subject") or "Your Shipment"

        logger.info(f"[confirmation_tools] Found shipment | status={current_status}")

        # Override detected_lang with DB value
        lang_meta     = shipment.get("language_metadata", {}) if shipment else {}
        detected_lang = (lang_meta.get("detected_language") or detected_lang) if isinstance(lang_meta, dict) else detected_lang

        operator_email = settings.OPERATOR_EMAIL
        all_fields     = REQUIRED_FIELDS + OPTIONAL_FIELDS
        customer_name  = (
            request_data.get("required", {}).get("customer_name") or
            request_data.get("customer_name") or
            "Customer"
        )

        # ── PRICING_PENDING: send reminder to operator ─────────────
        if current_status == "PRICING_PENDING":
            logger.info(f"[confirmation_tools] Sending pricing reminder to operator")
            reminder_html    = build_email(
                email_type    = "pricing",
                customer_name = "Operator",
                request_id    = request_id,
                request_data  = request_data,
                all_fields    = all_fields,
                pricing_details=[],
            )
            reminder_subject = f"[REMINDER] Pricing Required -- {request_id}"
            reminder_msg_id  = send_email(
                to         = operator_email,
                subject    = reminder_subject,
                body_html  = reminder_html,
                request_id = request_id,
            )
            await push_message_log(
                request_id      = request_id,
                message         = Message(
                    message_id   = reminder_msg_id,
                    sender_email = settings.GMAIL_ADDRESS,
                    sender_type  = "system",
                    direction    = "outgoing",
                    subject      = reminder_subject,
                    body         = "Pricing reminder sent to operator.",
                    received_at  = datetime.utcnow(),
                ).model_dump(),
                sent_message_id = reminder_msg_id,
                status          = "PRICING_PENDING",
            )
            return f"✅ Pricing reminder sent to operator | msg_id={reminder_msg_id} | status=PRICING_PENDING"

        # ── MISSING_INFO: redirect to extraction ───────────────────
        if current_status == "MISSING_INFO":
            logger.info(f"[confirmation_tools] Shipment still in MISSING_INFO — redirecting to extraction")
            return (
                f"⚠️ Shipment {request_id} is still in MISSING_INFO status. "
                f"The customer is providing missing field values, not confirming a quote. "
                f"Call extract_missing_field_values to extract the data from the email body."
            )

        # ── Non-QUOTED: cannot confirm ─────────────────────────────
        if current_status != "QUOTED":
            return f"❌ Cannot confirm shipment with status '{current_status}', expected 'QUOTED'"

        # ── Process confirmation ───────────────────────────────────

        # 1. Notify operator (always English)
        operator_html    = build_email(
            email_type    = "status",
            customer_name = "Operator",
            request_id    = request_id,
            request_data  = request_data,
            all_fields    = all_fields,
            status        = "CONFIRMED",
            message       = (
                f"The customer ({customer_name}) has confirmed the shipment. "
                "Please proceed with the logistics arrangements."
            ),
        )
        operator_subject = f"Customer Confirmed Shipment -- {request_id}"
        operator_msg_id  = send_email(
            to         = operator_email,
            subject    = operator_subject,
            body_html  = operator_html,
            request_id = request_id,
        )
        await push_message_log(
            request_id      = request_id,
            message         = Message(
                message_id   = operator_msg_id,
                sender_email = settings.GMAIL_ADDRESS,
                sender_type  = "system",
                direction    = "outgoing",
                subject      = operator_subject,
                body         = "Operator notified -- customer confirmed the shipment.",
                received_at  = datetime.utcnow(),
            ).model_dump(),
            sent_message_id = operator_msg_id,
            status          = "CONFIRMED",
        )

        # 2. Update status
        await update_shipment(request_id, {"status": "CONFIRMED"})

        # 3. Send thank-you to customer in their language
        customer_html    = build_email(
            email_type    = "status",
            customer_name = customer_name,
            request_id    = request_id,
            request_data  = request_data,
            all_fields    = all_fields,
            status        = "CONFIRMED",
            lang          = detected_lang,
            message       = (
                "Thank you for confirming your shipment with LogiAI. "
                "We are delighted to have you on board and will handle your shipment "
                "with the utmost care and professionalism."
            ),
            next_steps    = [
                "Our team will coordinate all logistics for your shipment",
                "You will receive regular updates on the shipment progress",
                "Feel free to contact us anytime with your Request ID for any queries",
            ]
        )
        customer_subject = f"Re: {subject} -- Shipment Confirmed"
        if detected_lang != "en":
            logger.info(f"[confirmation_tools] Translating confirmation email to '{detected_lang}' for {customer_email}")
            customer_html    = translate_to_language(customer_html, detected_lang)
            customer_subject = translate_text_to_language(customer_subject, detected_lang)

        customer_msg_id = send_email(
            to         = customer_email,
            subject    = customer_subject,
            body_html  = customer_html,
            request_id = request_id,
        )
        await push_message_log(
            request_id      = request_id,
            message         = Message(
                message_id   = customer_msg_id,
                sender_email = settings.GMAIL_ADDRESS,
                sender_type  = "system",
                direction    = "outgoing",
                subject      = customer_subject,
                body         = "Thank-you email sent to customer -- shipment confirmed.",
                received_at  = datetime.utcnow(),
            ).model_dump(),
            sent_message_id = customer_msg_id,
            status          = "CONFIRMED",
        )

        logger.info(f"[confirmation_tools] Confirmation processed for {request_id}")
        return (
            f"✅ Confirmation email sent to {customer_email} | "
            f"operator_msg_id={operator_msg_id} | "
            f"customer_msg_id={customer_msg_id} | "
            f"status=CONFIRMED"
        )

    except Exception as e:
        logger.error(f"[confirmation_tools] Error processing confirmation: {e}")
        return f"❌ Failed to process confirmation: {str(e)}"
