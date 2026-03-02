
from motor.motor_asyncio import AsyncIOMotorClient

client = None
db = None


async def connect_db(mongodb_uri: str, db_name: str):
    global client, db

    try:

        client = AsyncIOMotorClient(mongodb_uri)
        db = client[db_name]
        await client.admin.command("ping")
        print("MongoDB connected ✅")
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        raise


async def close_db():
    try:
        if client:
            client.close()
    except Exception as e:
        print(f"❌ Close error: {e}")
        raise


def get_db():
    try:
        if db is None:
            raise RuntimeError("Database not connected")
        return db

    except Exception as e:
        print(f"❌ get_db error: {e}")
        raise
