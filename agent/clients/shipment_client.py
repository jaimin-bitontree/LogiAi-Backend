"""
Shipment API client — all httpx calls to the shipment endpoints are centralised here.
The reqid node (and any other node) imports from this module instead of making
raw HTTP calls inline.
"""

import httpx
from config import settings
from typing import Optional

BASE_URL = settings.API_BASE_URL  # e.g. "http://localhost:8000"


async def fetch_shipment_by_thread(thread_id: str) -> Optional[dict]:
    """
    Call GET /shipments/by-thread/{thread_id}.
    Returns the shipment dict if found, or None if 404.
    Raises httpx.HTTPStatusError for any other non-2xx response.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/shipments/by-thread/{thread_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()


async def store_shipment_state(state: dict) -> dict:
    """
    Call POST /shipments/store with the agent state dict.
    Returns the response JSON { request_id, status }.
    Raises httpx.HTTPStatusError on failure.
    """
    payload = {
        "request_id":     state.get("request_id"),
        "thread_id":      state.get("thread_id"),
        "customer_email": state.get("customer_email"),
        "subject":        state.get("subject"),
        "body":           state.get("body", ""),
        "message_ids":    state.get("message_ids", []),
        "attachments":    state.get("attachments", []),
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/shipments/store", json=payload)
        response.raise_for_status()
        return response.json()
