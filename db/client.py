
from motor.motor_asyncio import AsyncIOMotorClient

client = None
db = None


async def connect_db(mongodb_uri: str, db_name: str):
    global client, db
    client = AsyncIOMotorClient(mongodb_uri)
    db = client[db_name]
    await client.admin.command("ping")
    print("MongoDB connected ✅")


async def close_db():
    if client:
        client.close()


def get_db():
    return db
