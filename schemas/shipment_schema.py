from pydantic import BaseModel
from typing import Optional, List


class StoreStateRequest(BaseModel):
    """Request body for POST /shipments/store — receives agent state after reqid node."""
    request_id: str
    thread_id: Optional[str] = None
    last_message_id: str
    customer_email: str
    subject: Optional[str] = None
    body: str = ""
    message_ids: Optional[List[str]] = []
    attachments: Optional[List] = []
    translated_body: Optional[str] = None
    translated_subject: Optional[str] = None
    language_metadata: Optional[dict] = None


class StoreStateResponse(BaseModel):
    """Response returned after storing state to DB."""
    request_id: str
    status: str


class ShipmentStateResponse(BaseModel):
    """Response returned by GET /shipments/by-thread/{thread_id} — used by node to hydrate state."""
    request_id: str
    thread_id: str
    last_message_id: str
    status: str
    intent: Optional[str] = None
    message_ids: List[str] = []
    attachments: List = []
