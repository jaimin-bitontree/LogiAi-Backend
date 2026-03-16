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


async def job():
    logger.info(f"⏳ Polling at {datetime.now()}")

    loop = asyncio.get_running_loop()

    try:
        # 🔹 Step 1: Fetch raw emails (IMAP is blocking)
        raw_emails = await loop.run_in_executor(
            None, fetch_unread_emails
        )

        logger.info(f"📬 Found {len(raw_emails)} emails")

        # 🔹 Step 2: Process each email through LangGraph (run_workflow is now async)
        for raw in raw_emails:

            try:
                # result = await run_workflow(raw)
                result = asyncio.create_task(run_workflow(raw))
                if result:
                    logger.info(f"✅ Processed: {result.get('subject')}")
                else:
                    logger.warning("⚠️  No result from workflow")

            except Exception as e:
                logger.error(f"❌ Failed to process email: {e}")

    except Exception as e:
        logger.error(f"❌ Polling error: {e}")


async def start_poller():
    try:
        if not scheduler.get_jobs():
            scheduler.add_job(job, "interval", minutes=1)

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

