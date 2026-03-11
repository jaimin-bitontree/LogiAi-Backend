import imaplib
import logging
from config import settings

logger = logging.getLogger(__name__)


def connect_gmail() -> imaplib.IMAP4_SSL:
    """
    Establish secure IMAP connection to Gmail.
    """
    try:
        mail = imaplib.IMAP4_SSL(settings.IMAP_GMAIL, settings.IMAP_PORT)
        mail.login(settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD)
        mail.select("inbox")
        return mail

    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP login failed: {e}")
        raise

    except OSError as e:
        logger.error(f"Network error: {e}")
        raise


def fetch_unread_emails() -> list[bytes]:
    """
    Fetch unread emails from Gmail.
    Returns:
        List of raw RFC822 email bytes.
    """

    raw_emails: list[bytes] = []
    mail = None

    try:
        mail = connect_gmail()

        # Search for unread emails
        status, message_ids = mail.search(None, "UNSEEN")

        if status != "OK":
            logger.error("Failed to search inbox.")
            return []

        if not message_ids or not message_ids[0]:
            logger.info("No new emails.")
            return []

        ids = message_ids[0].split()
        logger.info(f"Found {len(ids)} unread email(s).")

        for email_id in ids:
            status, data = mail.fetch(email_id, "(RFC822)")

            if status != "OK":
                logger.warning(f"Failed to fetch email ID {email_id}")
                continue

            if data and data[0]:
                raw_email = data[0][1]
                if not raw_email:
                    continue
            else:
                logger.error("No email data found, skipping...")
                continue

            if raw_email:
                raw_emails.append(raw_email)

                # Mark as read
                mail.store(email_id, "+FLAGS", "\\Seen")

    except Exception as e:
        logger.error(f"❌ Gmail receiver error: {e}")

    finally:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass

    return raw_emails
