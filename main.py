# main.py

import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from config.settings import settings
from db.client import connect_db, close_db
from utils.poller import start_poller, stop_poller
from api.shipment_router import router as shipment_router
from fastapi.middleware.cors import CORSMiddleware
# Configure logging to show in terminal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # This ensures logs appear in terminal
    ]
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # 🔹 Connect DB
        logger.info("🔌 Connecting to database...")
        await connect_db(settings.MONGODB_URI, settings.DB_NAME)
        logger.info("✅ Database connected")

        # 🔹 Start Poller
        logger.info("🚀 Starting Gmail poller...")
        await start_poller()
        logger.info("✅ Gmail poller startup complete")

        yield  # FastAPI runs here

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise
    finally:
        # 🔹 Stop Poller
        logger.info("🛑 Stopping Gmail poller...")
        stop_poller()

        # 🔹 Close DB
        logger.info("🔌 Closing database connection...")
        await close_db()
        logger.info("✅ Shutdown complete")




app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(shipment_router)



@app.get("/health")
async def health():
    return {"status": "ok"}
