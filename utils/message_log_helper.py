"""
utils/message_log_helper.py

Shared helper for building Message objects and pushing them to the DB log.
Avoids repeating the same Message(...).model_dump() + push_message_log() pattern
across every tool.
"""

import logging
from datetime import datetime

from config.settings import settings
from models.shipment import Message
from services.shipment.shipment_service import push_message_log

logger = logging.getLogger(__name__)


async def log_outgoing_message(
    request_id:  str,
    message_id:  str,
    subject:     str,
    body:        str,
    status:      str,
    sender_type: str = "system",
) -> Message:
    """
    Build a Message object for an outgoing email and push it to the DB log.

    Args:
        request_id:  Shipment request ID
        message_id:  Sent email Message-ID
        subject:     Email subject
        body:        Short description / body summary for the log
        status:      Shipment status to set after logging
        sender_type: Defaults to "system"

    Returns:
        The Message object that was logged.
    """
    msg = Message(
        message_id   = message_id,
        sender_email = settings.GMAIL_ADDRESS,
        sender_type  = sender_type,
        direction    = "outgoing",
        subject      = subject,
        body         = body,
        received_at  = datetime.utcnow(),
    )
    await push_message_log(
        request_id      = request_id,
        message         = msg.model_dump(),
        sent_message_id = message_id,
        status          = status,
    )
    logger.debug(f"[message_log_helper] Logged | request_id={request_id} | msg_id={message_id} | status={status}")
    return msg
