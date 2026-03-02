# main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI
from config import settings
from db.client import connect_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db(settings.MONGODB_URI, settings.DB_NAME)
    yield
    await close_db()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}
