import logging
import httpx
from agent.state import AgentState
from services.shipment_service import (
    find_by_thread_id,
    find_by_request_id,
    find_by_email_and_open_status,
    create_shipment,
    update_shipment_thread_id,
)
from models.shipment import Shipment
from utils.req_id_generator import generate_request_id

logger = logging.getLogger(__name__)


def _hydrate_state(state: AgentState, shipment: Shipment) -> AgentState:
    """Copy shipment fields into agent state, skipping null values."""
    shipment_dict = shipment.model_dump()
    for key, value in shipment_dict.items():
        if key in state and value is not None:
             state[key] = value

    print(state)
    return state


async def _safe_lookup(fn, *args):
    """Call a DB lookup function and swallow network/runtime errors."""
    try:
        return await fn(*args)
    except (httpx.HTTPStatusError, httpx.RequestError, Exception) as exc:
        logger.warning("DB lookup %s failed: %s", fn.__name__, exc)
        return None


async def generate_reqid(state: AgentState) -> AgentState:

    # thread_id (state)       = current Message-ID
    # conversation_id (state) = parent Message-ID (In-Reply-To)
    
    current_message_id = state.get("thread_id", "")
    conversation_id    = state.get("conversation_id", "")
    request_id         = state.get("request_id", "")
    customer_email     = state.get("customer_email", "")

    shipment = None

    # ── Step 1: Lookup by parent message ID ────────────────────────────────
    # If this message is a reply, its conversation_id is the parent message.
    # We find if any shipment has that parent as its thread_id (its latest message).
    if conversation_id:
        shipment = await _safe_lookup(find_by_thread_id, conversation_id)
        if shipment:
            logger.info("Step 1 HIT — matched by parent message ID (In-Reply-To): %s", conversation_id)

    # ── Step 2: Lookup by request_id ──────────────────────────────────────
    if not shipment and request_id:
        shipment = await _safe_lookup(find_by_request_id, request_id)
        if shipment:
            logger.info("Step 2 HIT — matched by request_id: %s", request_id)

    # ── Step 3: Lookup by email + open status ─────────────────────────────
    if not shipment and customer_email:
        shipment = await _safe_lookup(find_by_email_and_open_status, customer_email)
        if shipment:
            logger.info("Step 3 HIT — matched by email %s with status %s", customer_email, shipment.status)

    # ── Prepare Message Object ────────────────────────────────────────────
    from models.shipment import Message
    new_message = Message(
        message_id=current_message_id,
        sender_email=state.get("customer_email"),
        sender_type="customer",
        direction="incoming",
        subject=state.get("subject"),
        body=state.get("body", ""),
        attachments=state.get("attachments", [])
    )

    if shipment:
        # Existing shipment found — update it in DB and hydrate state
        # Set DB thread_id = current message
        await update_shipment_thread_id(
            shipment.request_id, 
            current_message_id, 
            attachments=state.get("attachments"),
            new_message=new_message.dict()
        )
        return _hydrate_state(state, shipment)

    # ── Step 4: Generate fresh request_id and store new shipment ──────────
    new_id = generate_request_id()
    state["request_id"] = new_id
    state["status"]     = "NEW"
    
    new_shipment = Shipment(
        request_id=new_id,
        thread_id=current_message_id, # This is the "head" / latest message for next lookup
        customer_email=customer_email,
        subject=state.get("subject"),
        body=state.get("body", ""),
        translated_body=state.get("translated_body", ""),
        translated_subject=state.get("translated_subject", ""),
        language_metadata=state.get("language_metadata"),
        intent=state.get("intent"),
        status="NEW",
        message_ids=[current_message_id] if current_message_id else [],
        attachments=state.get("attachments", []),
        messages=[new_message]
    )
    await create_shipment(new_shipment)
    
    logger.info("Step 4 — generated and stored new request_id: %s", new_id)
    return state

