"""
agent/tools/cancellation_tools.py
"""

import logging
from langchain_core.tools import tool

from config.settings import settings
from config.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from services.shipment.cancellation_service import verify_cancellation_eligibility
from services.email.email_sender import send_email
from services.email.email_template import build_email
from services.shipment.shipment_service import get_shipment_by_request_id, log_outgoing_message
from services.ai.language_service import translate_to_language, translate_text_to_language
from utils.language_helpers import get_detected_lang

logger = logging.getLogger(__name__)


@tool
async def cancel_shipment(request_id: str, customer_email: str) -> str:
    """Cancel a shipment request.

    Args:
        request_id: The shipment request ID
        customer_email: Customer email address

    Returns:
        Confirmation string with sent message ID
    """
    try:
        logger.info(f"[cancellation_tools] Processing cancellation for {request_id}")

        # 1. Verify eligibility
        verification = await verify_cancellation_eligibility(
            customer_email=customer_email,
            request_id=request_id,
        )

        if not verification["eligible"]:
            error_msg    = verification["error"]
            logger.warning(f"[cancellation_tools] Cancellation rejected: {error_msg}")

            shipment_doc  = await get_shipment_by_request_id(request_id)
            detected_lang = get_detected_lang(shipment_doc)

            email_body = build_email(
                email_type    = "status",
                customer_name = customer_email,
                request_id    = request_id or "N/A",
                status        = "CANCEL_REJECTED",
                message       = f"Your cancellation request could not be processed: {error_msg}",
            )
            out_subject = "Cancellation Request - Unable to Process"
            if detected_lang != "en":
                logger.info(f"[cancellation_tools] Translating rejection email to '{detected_lang}' for {customer_email}")
                email_body  = translate_to_language(email_body, detected_lang)
                out_subject = translate_text_to_language(out_subject, detected_lang)

            outgoing_message_id = send_email(
                to         = customer_email,
                subject    = out_subject,
                body_html  = email_body,
                request_id = request_id or "",
            )
            return f"❌ Cancellation rejected: {error_msg} | msg_id={outgoing_message_id}"

        # 2. Process cancellation
        shipment      = verification["shipment"]
        all_fields    = REQUIRED_FIELDS + OPTIONAL_FIELDS
        customer_name = shipment.request_data.get("customer_name") or customer_email

        shipment_doc  = await get_shipment_by_request_id(request_id)
        detected_lang = get_detected_lang(shipment_doc)

        email_body = build_email(
            email_type    = "status",
            customer_name = customer_name,
            request_id    = shipment.request_id,
            request_data  = shipment.request_data,
            all_fields    = all_fields,
            status        = "CANCELLED",
            lang          = detected_lang,
            message       = f"As per your request, shipment {shipment.request_id} has been successfully cancelled.",
        )
        out_subject = f"Shipment Cancelled 🛑 - {shipment.request_id}"

        if detected_lang != "en":
            logger.info(f"[cancellation_tools] Translating cancellation email to '{detected_lang}' for {customer_email}")
            email_body  = translate_to_language(email_body, detected_lang)
            out_subject = translate_text_to_language(out_subject, detected_lang)

        outgoing_message_id = send_email(
            to         = customer_email,
            subject    = out_subject,
            body_html  = email_body,
            request_id = shipment.request_id,
        )

        await log_outgoing_message(
            request_id = shipment.request_id,
            message_id = outgoing_message_id,
            subject    = out_subject,
            body       = f"Shipment {shipment.request_id} cancelled by user.",
            status     = "CANCELLED",
        )

        logger.info(f"[cancellation_tools] Shipment {shipment.request_id} cancelled")
        return f"✅ Cancellation email sent to {customer_email} | msg_id={outgoing_message_id} | status=CANCELLED"

    except Exception as e:
        logger.error(f"[cancellation_tools] Error processing cancellation: {e}")
        return f"❌ Failed to process cancellation: {str(e)}"
