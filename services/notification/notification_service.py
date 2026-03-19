import logging
from datetime import datetime
from config.settings import settings
from config.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import Message
from services.shipment.shipment_service import find_by_request_id, push_message_log
from services.email.email_sender import send_email
from services.email.email_template import build_email
from services.ai.language_service import translate_to_language, translate_text_to_language
from utils.language_helpers import get_detected_lang

logger = logging.getLogger(__name__)

async def send_quote_notification(request_id: str) -> dict:
    """Send notification email for quoted shipment in customer's language"""

    # Get shipment data
    shipment = await find_by_request_id(request_id)
    if not shipment:
        raise ValueError(f"Shipment {request_id} not found")

    if shipment.status != "QUOTED":
        raise ValueError(f"Shipment {request_id} is not in QUOTED status")

    # Get customer's detected language
    detected_lang = get_detected_lang(shipment.__dict__ if hasattr(shipment, '__dict__') else shipment)

    # Get customer name
    customer_name = (
        shipment.request_data.get("required", {}).get("customer_name")
        or shipment.request_data.get("customer_name")
        or shipment.customer_email
    )

    all_fields = REQUIRED_FIELDS + OPTIONAL_FIELDS

    # Build notification email (English first)
    html = build_email(
        email_type      = "status",
        customer_name   = customer_name,
        request_id      = shipment.request_id,
        request_data    = shipment.request_data,
        all_fields      = all_fields,
        status          = "QUOTED",
        message         = (
            "This is a reminder that your shipment quotation is ready and awaiting your confirmation. "
            "Please review the details and reply to confirm."
        ),
        next_steps      = [
            "Review the quotation details carefully",
            "Reply to this email with your confirmation",
            "Our team will proceed with your shipment once confirmed",
        ]
    )

    subject = f"Reminder: Your Quote is Ready — {shipment.request_id}"

    # Translate to customer's language if not English
    if detected_lang and detected_lang != "en":
        logger.info(
            f"[notification_service] Translating notification email to "
            f"'{detected_lang}' for {shipment.customer_email}"
        )
        html    = translate_to_language(html, detected_lang)
        subject = translate_text_to_language(subject, detected_lang)

    # Send email
    message_id = send_email(
        to         = shipment.customer_email,
        subject    = subject,
        body_html  = html,
        request_id = shipment.request_id
    )

    # Create message log
    notification_message = Message(
        message_id   = message_id,
        sender_email = settings.GMAIL_ADDRESS,
        sender_type  = "system",
        direction    = "outgoing",
        subject      = subject,
        body         = "Quote notification sent to customer",
        received_at  = datetime.utcnow()
    )

    # Update database
    await push_message_log(
        request_id      = shipment.request_id,
        message         = notification_message.model_dump(),
        sent_message_id = message_id,
        status          = "QUOTED"  # Keep same status
    )

    logger.info(
        f"[notification_service] Notification sent | "
        f"request_id={request_id} | msg_id={message_id} | lang={detected_lang}"
    )

    return {
        "message_id":    message_id,
        "customer_email": shipment.customer_email,
        "lang":          detected_lang,
    }