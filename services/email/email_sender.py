import base64
import time
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config.settings import settings
from utils.gmail_auth import get_gmail_service

logger = logging.getLogger(__name__)


def generate_message_id(request_id: str = "") -> str:
    """
    Generate a readable unique Message-ID WITHOUT angle brackets.
    Format: LOGIAI-{request_id}-{timestamp}@logiai.com
    """
    timestamp = int(time.time())
    prefix = f"LOGIAI-{request_id}-" if request_id else "LOGIAI-"
    return f"{prefix}{timestamp}@logiai.com"


def send_email(to: str, subject: str, body_html: str, request_id: str = "") -> str:
    """
    Send an HTML email via Gmail API (OAuth2).

    Args:
        to:         Recipient email address.
        subject:    Email subject line.
        body_html:  HTML content of the email body.
        request_id: Optional shipment ID to embed in the Message-ID.

    Returns:
        The Message-ID of the sent email WITHOUT angle brackets.

    Raises:
        RuntimeError: If the email fails to send.
    """
    message_id = generate_message_id(request_id)

    msg = MIMEMultipart("alternative")
    msg["From"]       = settings.GMAIL_ADDRESS
    msg["To"]         = to
    msg["Subject"]    = subject
    msg["Message-ID"] = f"<{message_id}>"

    # Plain text fallback for operator emails
    if request_id:
        plain_text = f"""
LogiAI — Shipment Management

Request ID: {request_id}

{subject}

Please reply to this email with your response.
For operator emails: Include pricing details in your reply.

This is an automated message from LogiAI.
        """.strip()
        msg.attach(MIMEText(plain_text, "plain"))

    msg.attach(MIMEText(body_html, "html"))

    try:
        service = get_gmail_service()

        # Gmail API requires base64url encoded raw message
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        result = service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        logger.info(f"Email sent to {to} | Message-ID: {message_id} | Gmail ID: {result.get('id')}")
        return message_id

    except Exception as e:
        logger.error(f"Gmail API error sending to {to}: {e}")
        raise RuntimeError(f"Failed to send email: {e}") from e
