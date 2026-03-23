from fastapi import APIRouter, Header, HTTPException
from config.settings import settings
from utils.poller import job

router = APIRouter(prefix="/cron", tags=["cron"])

@router.post("/poll")
async def cron_poll():
    
    await job()
    return {"status": "ok", "message": "Polling job triggered"}
