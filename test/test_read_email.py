from services.gmail_receiver import fetch_unread_emails
import logging

logger = logging.getLogger(__name__)

logger.info("🔍 Checking Gmail inbox for unread emails...")

emails = fetch_unread_emails()
logger.debug(f"Fetched emails: {emails}")

if not emails:
    logger.info("📭 No unread emails found")
else:
    logger.info(f"📬 Found {len(emails)} email(s)")

    for i, email in enumerate(emails, 1):
        logger.info(f"{'='*50}")
        logger.info(f"Email {i}:")
        logger.info(f"  From:      {email['sender_email']}")
        logger.info(f"  Subject:   {email['subject']}")
        logger.info(f"  Thread ID: {email['thread_id'] or 'None (fresh email)'}")
        logger.info(f"  Message ID: {email['message_id']}")
        logger.info(f"  Body:\n{email['body'][:]}")
        logger.info(f"  Attachments: {email['attachments'] or 'None'}")
        logger.info(f"{'='*50}")