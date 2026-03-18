"""
agent/tools/email_tools.py
"""

import logging
from langchain_core.tools import tool

from config.settings import settings
from config.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS, PACKAGE_TYPES, CONTAINER_TYPES, INCOTERMS, SHIPMENT_TYPES, TRANSPORT_MODES
from services.email.email_sender import send_email
from services.email.email_template import build_email
from services.shipment.shipment_service import get_request_data, get_shipment_by_request_id
from services.ai.language_service import translate_to_language, translate_text_to_language
from utils.language_helpers import get_detected_lang
from utils.message_log_helper import log_outgoing_message

logger = logging.getLogger(__name__)


@tool
async def send_missing_info_email(
    request_id:     str,
    customer_email: str,
    customer_name:  str,
    subject:        str,
    missing_fields: list,
) -> str:
    """
    Sends an email to the customer requesting missing shipment fields,
    then logs the sent email to the database.

    Call this when extract_shipment_fields returns is_valid=False.

    Args:
        request_id: The shipment request ID (e.g. REQ-2026-...)
        customer_email: Customer email address
        customer_name: Customer name for the greeting
        subject: Original email subject line
        missing_fields: List of required field names still missing

    Returns: Confirmation string with sent message ID.
    """
    request_data  = await get_request_data(request_id)
    all_fields    = REQUIRED_FIELDS + OPTIONAL_FIELDS
    shipment_doc  = await get_shipment_by_request_id(request_id)
    detected_lang = get_detected_lang(shipment_doc)

    field_options = {
        "package_type":   PACKAGE_TYPES,
        "container_type": CONTAINER_TYPES,
        "incoterm":       INCOTERMS,
        "shipment_type":  SHIPMENT_TYPES,
        "transport_mode": TRANSPORT_MODES,
    }

    html = build_email(
        email_type     = "missing_info",
        customer_name  = customer_name,
        request_id     = request_id,
        request_data   = request_data,
        missing_fields = missing_fields,
        field_options  = field_options,
        all_fields     = all_fields,
        lang           = detected_lang,
        next_steps     = [
            "Review the missing fields listed above",
            "Reply directly to this email with the required information",
            "Once received, we will proceed with your quotation",
        ]
    )

    additional_info_msg = "Additional Information Required"
    if detected_lang != "en":
        logger.info(f"[email_tools] Translating missing_info email to '{detected_lang}' for {customer_email}")
        html                = translate_to_language(html, detected_lang)
        subject             = translate_text_to_language(subject, detected_lang)
        additional_info_msg = translate_text_to_language(additional_info_msg, detected_lang)

    email_subject   = f"Re: {subject} — {additional_info_msg}"
    sent_message_id = send_email(
        to         = customer_email,
        subject    = email_subject,
        body_html  = html,
        request_id = request_id,
    )

    await log_outgoing_message(
        request_id = request_id,
        message_id = sent_message_id,
        subject    = email_subject,
        body       = f"Missing fields: {', '.join(missing_fields)}",
        status     = "MISSING_INFO",
    )

    logger.info("[email_tools] Missing info email sent | request_id=%s | msg_id=%s | lang=%s",
                request_id, sent_message_id, detected_lang)
    return f"✅ Missing info email sent | msg_id={sent_message_id} | status=MISSING_INFO"


@tool
async def send_complete_info_emails(
    request_id:     str,
    customer_email: str,
    customer_name:  str,
    subject:        str,
) -> str:
    """
    Sends TWO emails when all required shipment fields are provided:
      1. A PRICING_PENDING confirmation to the customer (in their language).
      2. A full shipment details summary to the operator (always English).

    Call this when extract_shipment_fields returns is_valid=True.

    Args:
        request_id: The shipment request ID
        customer_email: Customer email address
        customer_name: Customer name
        subject: Original email subject

    Returns: Confirmation string with both sent message IDs.
    """
    request_data   = await get_request_data(request_id)
    all_fields     = REQUIRED_FIELDS + OPTIONAL_FIELDS
    operator_email = settings.OPERATOR_EMAIL

    shipment_doc  = await get_shipment_by_request_id(request_id)
    detected_lang = get_detected_lang(shipment_doc)

    # ── Customer confirmation email ────────────────────────────
    customer_html = build_email(
        email_type    = "status",
        customer_name = customer_name,
        request_id    = request_id,
        request_data  = request_data,
        all_fields    = all_fields,
        status        = "PRICING_PENDING",
        lang          = detected_lang,
        message       = (
            "We have received all the information needed for your shipment request. "
            "Our team is reviewing the details and you will receive a quotation shortly."
        ),
        next_steps    = [
            "Our team will review your request thoroughly",
            "We will prepare a detailed pricing proposal",
            "You will receive our response shortly",
        ]
    )
    customer_subject = f"Re: {subject} — Request Received"

    if detected_lang != "en":
        logger.info(f"[email_tools] Translating complete_info email to '{detected_lang}' for {customer_email}")
        customer_html    = translate_to_language(customer_html, detected_lang)
        customer_subject = translate_text_to_language(customer_subject, detected_lang)

    customer_msg_id = send_email(
        to         = customer_email,
        subject    = customer_subject,
        body_html  = customer_html,
        request_id = request_id,
    )

    # ── Operator notification email (always English) ───────────
    if not operator_email:
        logger.error("[email_tools] OPERATOR_EMAIL not configured")
        return f"✅ Customer email sent | customer_msg_id={customer_msg_id} | ❌ Operator email failed: not configured"

    try:
        operator_html    = build_email(
            email_type    = "pricing",
            customer_name = "Operator",
            request_id    = request_id,
            request_data  = request_data,
            all_fields    = all_fields,
        )
        operator_subject = f"New Shipment Request — {request_id}"
        operator_msg_id  = send_email(
            to         = operator_email,
            subject    = operator_subject,
            body_html  = operator_html,
            request_id = request_id,
        )
        logger.info(f"[email_tools] Operator email sent: {operator_msg_id}")
    except Exception as e:
        logger.error(f"[email_tools] Operator email failed: {e}")
        return f"✅ Customer email sent | customer_msg_id={customer_msg_id} | ❌ Operator email failed: {e}"

    # ── Log both to DB ─────────────────────────────────────────
    await log_outgoing_message(
        request_id = request_id,
        message_id = customer_msg_id,
        subject    = customer_subject,
        body       = "Confirmation sent to customer — all fields received.",
        status     = "PRICING_PENDING",
    )
    await log_outgoing_message(
        request_id = request_id,
        message_id = operator_msg_id,
        subject    = operator_subject,
        body       = "Operator notified — awaiting pricing reply.",
        status     = "PRICING_PENDING",
    )

    logger.info("[email_tools] Complete emails sent | request_id=%s | customer=%s | operator=%s | lang=%s",
                request_id, customer_msg_id, operator_msg_id, detected_lang)
    return (
        f"✅ Both emails sent | "
        f"customer_msg_id={customer_msg_id} | "
        f"operator_msg_id={operator_msg_id} | "
        f"status=PRICING_PENDING"
    )
