"""
agent/tools/email_tools.py

LangChain tools for sending emails.
SELF-CONTAINED: each tool fetches request_data from DB by request_id,
sends the email, and logs it to the DB — all internally.

The LLM only passes small scalar args (request_id, customer_email, etc.)
— NO large dict payloads to reconstruct.
"""

import logging
from datetime import datetime
from langchain_core.tools import tool

from config.settings import settings
from config.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import Message
from services.email.email_sender import send_email
from services.email.email_template import build_email
from services.shipment.shipment_service import push_message_log, get_request_data

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
    # Fetch extracted data from DB (saved by extraction tool)
    request_data = await get_request_data(request_id)
    all_fields   = REQUIRED_FIELDS + OPTIONAL_FIELDS

    html = build_email(
        email_type     = "missing_info",
        customer_name  = customer_name,
        request_id     = request_id,
        request_data   = request_data,
        missing_fields = missing_fields,
        all_fields     = all_fields,
        next_steps     = [
            "Review the missing fields listed above",
            "Reply directly to this email with the required information",
            "Once received, we will proceed with your quotation",
        ]
    )
    email_subject   = f"Re: {subject} — Additional Information Required"
    sent_message_id = send_email(
        to         = customer_email,
        subject    = email_subject,
        body_html  = html,
        request_id = request_id,
    )

    message_log = Message(
        message_id   = sent_message_id,
        sender_email = settings.GMAIL_ADDRESS,
        sender_type  = "system",
        direction    = "outgoing",
        subject      = email_subject,
        body         = f"Missing fields: {', '.join(missing_fields)}",
        received_at  = datetime.utcnow(),
    )

    await push_message_log(
        request_id      = request_id,
        message         = message_log.model_dump(),
        sent_message_id = sent_message_id,
        status          = "MISSING_INFO",
    )

    logger.info("[email_tools] Missing info email sent | request_id=%s | msg_id=%s", request_id, sent_message_id)
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
      1. A PRICING_PENDING confirmation to the customer.
      2. A full shipment details summary to the operator.

    Then logs both emails to the database automatically.

    Call this when extract_shipment_fields returns is_valid=True.

    Args:
        request_id: The shipment request ID
        customer_email: Customer email address
        customer_name: Customer name
        subject: Original email subject

    Returns: Confirmation string with both sent message IDs.
    """
    # Fetch extracted data from DB (saved by extraction tool)
    request_data   = await get_request_data(request_id)
    all_fields     = REQUIRED_FIELDS + OPTIONAL_FIELDS
    operator_email = settings.OPERATOR_EMAIL

    # ── Customer confirmation email ────────────────────────────
    customer_html = build_email(
        email_type    = "status",
        customer_name = customer_name,
        request_id    = request_id,
        request_data  = request_data,
        all_fields    = all_fields,
        status        = "PRICING_PENDING",
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
    customer_subject = f"Re: {subject} — Request Received ✅"
    customer_msg_id  = send_email(
        to         = customer_email,
        subject    = customer_subject,
        body_html  = customer_html,
        request_id = request_id,
    )

    # ── Operator notification email ────────────────────────────
    logger.debug(f"OPERATOR_EMAIL from settings: '{operator_email}'")
    logger.info(f"[email_tools] Sending operator notification to: {operator_email}")
    
    if not operator_email:
        error_msg = "OPERATOR_EMAIL not configured in settings"
        logger.error(f"[email_tools] {error_msg}")
        logger.error(f"{error_msg}")
        return f"✅ Customer email sent | customer_msg_id={customer_msg_id} | ❌ Operator email failed: {error_msg}"
    
    try:
        logger.debug(f"Building operator email template...")
        operator_html = build_email(
            email_type      = "pricing",
            customer_name   = "Operator",
            request_id      = request_id,
            request_data    = request_data,
            all_fields      = all_fields,
        )
        operator_subject = f"New Shipment Request — {request_id}"
        logger.debug(f"Operator email template built successfully")
        
        logger.debug(f"Attempting to send operator email to: {operator_email}")
        logger.info(f"[email_tools] Attempting to send operator email...")
        operator_msg_id = send_email(
            to         = operator_email,
            subject    = operator_subject,
            body_html  = operator_html,
            request_id = request_id,
        )
        logger.debug(f"Operator email sent successfully: {operator_msg_id}")
        logger.info(f"[email_tools] Operator email sent successfully: {operator_msg_id}")
    except Exception as e:
        error_msg = f"Failed to send operator email: {e}"
        logger.error(f"[email_tools] {error_msg}")
        logger.error(f"[email_tools] Operator email details - to: {operator_email}, subject: {operator_subject}")
        logger.error(f"{error_msg}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception details: {str(e)}")
        # Continue with customer email only
        return f"✅ Customer email sent | customer_msg_id={customer_msg_id} | ❌ Operator email failed: {e}"

    # ── Log both to DB ─────────────────────────────────────────
    customer_log = Message(
        message_id   = customer_msg_id,
        sender_email = settings.GMAIL_ADDRESS,
        sender_type  = "system",
        direction    = "outgoing",
        subject      = customer_subject,
        body         = "Confirmation sent to customer — all fields received.",
        received_at  = datetime.utcnow(),
    )
    operator_log = Message(
        message_id   = operator_msg_id,
        sender_email = settings.GMAIL_ADDRESS,
        sender_type  = "system",
        direction    = "outgoing",
        subject      = operator_subject,
        body         = "Operator notified — awaiting pricing reply.",
        received_at  = datetime.utcnow(),
    )

    await push_message_log(
        request_id      = request_id,
        message         = customer_log.model_dump(),
        sent_message_id = customer_msg_id,
        status          = "PRICING_PENDING",
    )
    await push_message_log(
        request_id      = request_id,
        message         = operator_log.model_dump(),
        sent_message_id = operator_msg_id,
        status          = "PRICING_PENDING",
    )

    logger.info("[email_tools] Complete emails sent | request_id=%s | customer=%s | operator=%s",
                request_id, customer_msg_id, operator_msg_id)
    return (
        f"✅ Both emails sent | "
        f"customer_msg_id={customer_msg_id} | "
        f"operator_msg_id={operator_msg_id} | "
        f"status=PRICING_PENDING"
    )
