# main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI
from config import settings
from db.client import connect_db, close_db
from utils.poller import start_poller, stop_poller
from api.shipment_router import router as shipment_router


@asynccontextmanager
async def lifespan(app: FastAPI):

    # 🔹 Connect DB
    await connect_db(settings.MONGODB_URI, settings.DB_NAME)

    # 🔹 Start Poller
    start_poller()

    yield  # FastAPI runs here

    # 🔹 Stop Poller
    stop_poller()

    # 🔹 Close DB
    await close_db()


app = FastAPI(lifespan=lifespan)

app.include_router(shipment_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
