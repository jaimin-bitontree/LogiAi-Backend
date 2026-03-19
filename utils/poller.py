# services/poller.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
from datetime import datetime
from services.email.gmail_receiver import fetch_unread_emails
from utils.email.email_utils import extract_message_id
from agent.workflow import run_workflow
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# Semaphore to limit concurrent email processing to 3
EMAIL_SEMAPHORE = asyncio.Semaphore(3)


def mark_single_email_as_seen(message_id: str):
    """Mark single email as seen by Message-ID"""
    from services.email.gmail_receiver import connect_gmail
    
    mail = None
    try:
        mail = connect_gmail()
        
        # Search for email by Message-ID
        status, email_ids = mail.search(None, f'HEADER Message-ID "{message_id}"')
        
        if status == "OK" and email_ids[0]:
            email_id = email_ids[0].split()[0]  # Get first match
            # Mark as seen
            mail.store(email_id, "+FLAGS", "\\Seen")
            logger.info(f"✅ Marked as seen: {message_id}")
        else:
            logger.warning(f"⚠️ Email not found for marking: {message_id}")
    
    except Exception as e:
        logger.error(f"❌ Failed to mark email as seen {message_id}: {e}")
    
    finally:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass


async def process_email_with_limit(raw_email):
    """Process single email with semaphore limit and immediate marking"""
    async with EMAIL_SEMAPHORE:
        try:
            result = await run_workflow(raw_email)
            
            # Mark as seen immediately after this email succeeds
            if result:
                message_id = extract_message_id(raw_email)
                mark_single_email_as_seen(message_id)
                logger.info(f"✅ Email processed and marked as seen")
            
            return result
        except Exception as e:
            logger.error(f"❌ Failed to process email: {e}")
            # Don't mark as seen if failed - email stays unread for retry
            return None


async def job():
    logger.info(f"⏳ Polling at {datetime.now()}")

    try:
        # 🔹 Step 1: Fetch raw emails (IMAP is blocking)
        raw_emails = await asyncio.get_event_loop().run_in_executor(
            None, fetch_unread_emails
        )

        logger.info(f"📬 Found {len(raw_emails)} emails")

        if not raw_emails:
            return

        # 🔹 Step 2: Process emails with semaphore limit (max 3 concurrent)
        # Each email gets marked as seen immediately after successful processing
        tasks = []
        for raw in raw_emails:
            task = asyncio.create_task(process_email_with_limit(raw))
            tasks.append(task)

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log final results (emails already marked individually)
        successful_count = 0
        failed_count = 0
        for i, result in enumerate(results):
            if result and not isinstance(result, Exception):
                successful_count += 1
                logger.info(f"✅ Email {i+1} processed successfully")
            else:
                failed_count += 1
                logger.error(f"❌ Email {i+1} failed to process")
        
        logger.info(f"📊 Batch complete: {successful_count} successful, {failed_count} failed")

    except Exception as e:
        logger.error(f"❌ Polling error: {e}")


async def start_poller():
    try:
        if not scheduler.get_jobs():
            scheduler.add_job(job, "interval", minutes=30)

        scheduler.start()
        logger.info("🚀 Gmail Poller started")
        
        # Run the first job immediately
        logger.info("🔄 Running initial polling job...")
        try:
            await job()
            logger.info("✅ Initial polling job completed successfully")
        except Exception as e:
            logger.error(f"❌ Initial polling job failed: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Don't raise here - let the scheduler handle future jobs
        
    except Exception as e:
        logger.error(f"❌ Failed to start poller: {e}")
        raise


def stop_poller():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("🛑 Gmail Poller stopped")

