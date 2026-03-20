"""
services/email/gmail_receiver.py

Fetch and mark emails using Gmail API (OAuth2).
Replaces the old imaplib-based implementation.
"""

import base64
import logging
from typing import List
from utils.gmail_auth import get_gmail_service

logger = logging.getLogger(__name__)


def fetch_unread_emails() -> List[bytes]:
    """
    Fetch unread emails from Gmail inbox using Gmail API.

    Returns:
        List of raw email bytes in RFC822 format
        (same format as the old imaplib implementation).
    """
    raw_emails: List[bytes] = []

    try:
        service = get_gmail_service()

        # Search unread emails in inbox
        results = service.users().messages().list(
            userId="me",
            q="is:unread in:inbox",
            maxResults=50
        ).execute()

        messages = results.get("messages", [])

        if not messages:
            logger.info("No new emails.")
            return []

        logger.info(f"Found {len(messages)} unread email(s).")

        for msg in messages:
            try:
                # Fetch full raw RFC822 content
                full_msg = service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="raw"
                ).execute()

                # Decode base64url → raw bytes (same as imaplib output)
                raw_email = base64.urlsafe_b64decode(full_msg["raw"])
                raw_emails.append(raw_email)

            except Exception as e:
                logger.warning(f"Failed to fetch message {msg['id']}: {e}")
                continue

        logger.info(f"Fetched {len(raw_emails)} email(s) successfully")

    except Exception as e:
        logger.error(f"❌ Gmail API receiver error: {e}")

    return raw_emails


def mark_single_email_as_seen(message_id: str):
    """
    Mark a single email as read using its Message-ID header.

    Args:
        message_id: Message-ID header value (without angle brackets)
    """
    try:
        service = get_gmail_service()

        # Search by Message-ID header
        results = service.users().messages().list(
            userId="me",
            q=f"rfc822msgid:{message_id}",
            maxResults=1
        ).execute()

        messages = results.get("messages", [])

        if not messages:
            logger.warning(f"⚠️ Email not found for marking: {message_id}")
            return

        gmail_id = messages[0]["id"]

        # Remove UNREAD label = mark as read
        service.users().messages().modify(
            userId="me",
            id=gmail_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()

        logger.info(f"✅ Marked as seen: {message_id}")

    except Exception as e:
        logger.error(f"❌ Failed to mark email as seen {message_id}: {e}")
