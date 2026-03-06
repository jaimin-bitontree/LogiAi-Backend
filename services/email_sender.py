import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import settings


def generate_message_id(request_id: str = "") -> str:
    """
    Generate a readable unique Message-ID.
    Format: <LOGIAI-{request_id}-{timestamp}@logiai.com>
    Example: <LOGIAI-REQ001-1741244400@logiai.com>
    """
    timestamp = int(time.time())
    prefix    = f"LOGIAI-{request_id}-" if request_id else "LOGIAI-"
    return f"<{prefix}{timestamp}@logiai.com>"


def send_email(to: str, subject: str, body_html: str, request_id: str = "") -> str:
    """
    Send an HTML email via Gmail SMTP.

    Args:
        to:         Recipient email address.
        subject:    Email subject line.
        body_html:  HTML content of the email body.
        request_id: Optional shipment ID to embed in the Message-ID.

    Returns:
        The Message-ID of the sent email (used for tracking/threading).

    Raises:
        RuntimeError: If the email fails to send.
    """
    message_id = generate_message_id(request_id)

    msg = MIMEMultipart("alternative")
    msg["From"]       = settings.GMAIL_ADDRESS
    msg["To"]         = to
    msg["Subject"]    = subject
    msg["Message-ID"] = message_id

    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD)
            server.sendmail(settings.GMAIL_ADDRESS, to, msg.as_string())

        print(f"✅ Email sent to {to} | Message-ID: {message_id}")
        return message_id

    except smtplib.SMTPException as e:
        print(f"❌ SMTP error while sending email to {to}: {e}")
        raise RuntimeError(f"Failed to send email: {e}") from e

    except Exception as e:
        print(f"❌ Unexpected error while sending email: {e}")
        raise RuntimeError(f"Failed to send email: {e}") from e
