
import logging
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

client = None
db = None


async def connect_db(mongodb_uri: str, db_name: str):
    global client, db

    try:

        client = AsyncIOMotorClient(mongodb_uri)
        db = client[db_name]
        await client.admin.command("ping")
        logger.info("MongoDB connected successfully")
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        raise


async def close_db():
    try:
        if client:
            client.close()
    except Exception as e:
        logger.error(f"Close error: {e}")
        raise


def get_db():
    try:
        if db is None:
            raise RuntimeError("Database not connected")
        return db

    except Exception as e:
        logger.error(f"get_db error: {e}")
        raise
