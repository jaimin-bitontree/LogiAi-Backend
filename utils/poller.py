# services/poller.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
from datetime import datetime
from services.gmail_receiver import fetch_unread_emails
from services.shipment_service import message_id_already_processed
from utils.email_utils import extract_message_id
from agent.workflow import run_workflow


scheduler = AsyncIOScheduler()


async def job():
    print(f"\n⏳ Polling at {datetime.now()}")

    loop = asyncio.get_running_loop()

    try:
        # 🔹 Step 1: Fetch raw emails (IMAP is blocking)
        raw_emails = await loop.run_in_executor(
            None, fetch_unread_emails
        )

        print(f"📬 Found {len(raw_emails)} emails")

        # 🔹 Step 2: Process each email through LangGraph
        for raw in raw_emails:

            try:
                # 🔹 Dedup check: skip if Message-ID already in DB
                message_id = extract_message_id(raw)
                if message_id and await message_id_already_processed(message_id):
                    print(f"⏭️  Skipping already-processed email: {message_id}")
                    continue

                result = await run_workflow(raw)
                if result:
                    print(f"✅ Processed: {result.get('subject')}")
                else:
                    print("⚠️  No result from workflow")

            except Exception as e:
                print(f"❌ Failed to process email: {e}")

    except Exception as e:
        print(f"❌ Polling error: {e}")


def start_poller():
    if not scheduler.get_jobs():
        scheduler.add_job(job, "interval", minutes=1)

    scheduler.start()

    # Run immediately once
    asyncio.create_task(job())

    print("🚀 Gmail Poller started")


def stop_poller():
    if scheduler.running:
        scheduler.shutdown()
        print("🛑 Gmail Poller stopped")

