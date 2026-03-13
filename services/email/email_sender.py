import smtplib
import time
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config.settings import settings

logger = logging.getLogger(__name__)


def generate_message_id(request_id: str = "") -> str:
    """
    Generate a readable unique Message-ID WITHOUT angle brackets.
    Format: LOGIAI-{request_id}-{timestamp}@logiai.com
    Example: LOGIAI-REQ001-1741244400@logiai.com
    
    Note: Angle brackets are added by the email library when sending.
    """
    timestamp = int(time.time())
    prefix    = f"LOGIAI-{request_id}-" if request_id else "LOGIAI-"
    return f"{prefix}{timestamp}@logiai.com"


def send_email(to: str, subject: str, body_html: str, request_id: str = "") -> str:
    """
    Send an HTML email via Gmail SMTP with plain text alternative.

    Args:
        to:         Recipient email address.
        subject:    Email subject line.
        body_html:  HTML content of the email body.
        request_id: Optional shipment ID to embed in the Message-ID.

    Returns:
        The Message-ID of the sent email WITHOUT angle brackets (used for tracking/threading).

    Raises:
        RuntimeError: If the email fails to send.
    """
    message_id = generate_message_id(request_id)

    msg = MIMEMultipart("alternative")
    msg["From"]       = settings.GMAIL_ADDRESS
    msg["To"]         = to
    msg["Subject"]    = subject
    msg["Message-ID"] = f"<{message_id}>"  # Add angle brackets for email header

    # Add plain text version with request_id for operator emails
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
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD)
            server.sendmail(settings.GMAIL_ADDRESS, to, msg.as_string())

        logger.info(f"Email sent to {to} | Message-ID: {message_id}")
        return message_id  # Return WITHOUT angle brackets

    except smtplib.SMTPException as e:
        logger.error(f"SMTP error while sending email to {to}: {e}")
        raise RuntimeError(f"Failed to send email: {e}") from e

    except Exception as e:
        logger.error(f"Unexpected error while sending email: {e}")
        raise RuntimeError(f"Failed to send email: {e}") from e
