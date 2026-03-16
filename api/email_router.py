import logging
import asyncio
from fastapi import APIRouter
from services.email.gmail_receiver import fetch_unread_emails
from agent.workflow import run_workflow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["email"])


@router.post("/process-emails")
async def process_emails():
    """Triggered by external cron job to process unread emails"""
    try:
        logger.info("⏳ Processing emails via cron job...")
        
        # Fetch unread emails from Gmail
        raw_emails = await asyncio.get_running_loop().run_in_executor(
            None, fetch_unread_emails
        )
        logger.info(f"📬 Found {len(raw_emails)} emails")
        
        # Process each email through workflow
        for raw in raw_emails:
            try:
                result = await run_workflow(raw)
                if result:
                    logger.info(f"✅ Processed: {result.get('subject')}")
                else:
                    logger.warning("⚠️ No result from workflow")
            except Exception as e:
                logger.error(f"❌ Failed to process email: {e}")
        
        return {"status": "ok", "processed": len(raw_emails)}
    
    except Exception as e:
        logger.error(f"❌ Cron job error: {e}")
        return {"status": "error", "error": str(e)}
