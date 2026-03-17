import logging
from datetime import datetime
from config.settings import settings
from config.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import Message
from services.shipment.shipment_service import find_by_request_id, push_message_log
from services.email.email_sender import send_email
from services.email.email_template import build_email

logger = logging.getLogger(__name__)

async def send_quote_notification(request_id: str) -> dict:
    """Send notification email for quoted shipment"""
    
    # Get shipment data
    shipment = await find_by_request_id(request_id)
    if not shipment:
        raise ValueError(f"Shipment {request_id} not found")
    
    if shipment.status != "QUOTED":
        raise ValueError(f"Shipment {request_id} is not in QUOTED status")
    
    # Build notification email
    customer_name = shipment.request_data.get("customer_name") or shipment.customer_email
    
    email_body = build_email(
        email_type="notification",
        customer_name=customer_name,
        request_id=shipment.request_id,
        request_data=shipment.request_data,
        pricing_details=shipment.pricing_details,
        all_fields=REQUIRED_FIELDS + OPTIONAL_FIELDS
    )
    
    # Send email
    subject = f"Reminder: Your Quote is Ready - {shipment.request_id}"
    message_id = send_email(
        to=shipment.customer_email,
        subject=subject,
        body_html=email_body,
        request_id=shipment.request_id
    )
    
    # Create message log
    notification_message = Message(
        message_id=message_id,
        sender_email=settings.GMAIL_ADDRESS,
        sender_type="system",
        direction="outgoing",
        subject=subject,
        body="Quote notification sent to customer",
        received_at=datetime.utcnow()
    )
    
    # Update database
    await push_message_log(
        request_id=shipment.request_id,
        message=notification_message.model_dump(),
        sent_message_id=message_id,
        status="QUOTED"  # Keep same status
    )
    
    logger.info(f"Notification sent for {request_id} | msg_id: {message_id}")
    
    return {
        "message_id": message_id,
        "customer_email": shipment.customer_email
    }