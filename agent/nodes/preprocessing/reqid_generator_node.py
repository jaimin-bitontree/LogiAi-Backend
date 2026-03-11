import logging
from agent.state import AgentState
from services.shipment.shipment_service import (
    find_by_any_message_id,
    find_by_last_message_id,
    find_by_request_id,
    find_by_email_and_open_status,
    create_shipment,
    update_shipment_thread_id,
)
from models.shipment import Shipment
from utils.req_id_generator import generate_request_id

logger = logging.getLogger(__name__)


def _hydrate_state(state: AgentState, shipment: Shipment) -> AgentState:
    """Copy shipment fields into agent state, preserving the latest incoming email content."""
    shipment_dict = shipment.model_dump()
    
    # FIELDS TO PRESERVE (The latest data from the new incoming email)
    # These were set by parser, language, and intent nodes; we don't want to overwrite them with old DB values.
    preserve = ["body", "translated_body", "translated_subject", "thread_id", "conversation_id", "messages", "intent"]
    
    for key, value in shipment_dict.items():
        if key in preserve:
            continue
        if key in state and value is not None:
             state[key] = value

    return state


async def _safe_lookup(fn, *args):
    """Call a DB lookup function and swallow network/runtime errors."""
    try:
        return await fn(*args)
    except (httpx.HTTPStatusError, httpx.RequestError, Exception) as exc:
        logger.warning("DB lookup %s failed: %s", fn.__name__, exc)
        return None


async def generate_reqid(state: AgentState) -> AgentState:
    """
    Improved lookup strategy using thread_id (conversation root) and message_ids array.
    
    Lookup order:
      1. Check if current message already processed (dedup)
      2. Check if In-Reply-To matches thread_id (conversation root)
      3. Check if In-Reply-To exists in message_ids array (any message in conversation)
      4. Check by request_id in email body
      5. Fallback to email + open status (customers only)
      6. Create new shipment (customers only)
    """

    # thread_id (state)       = current Message-ID
    # conversation_id (state) = parent Message-ID (In-Reply-To)
    
    current_message_id = state.get("thread_id", "")
    conversation_id    = state.get("conversation_id", "")
    request_id         = state.get("request_id", "")
    customer_email     = state.get("customer_email", "")
    is_operator        = state.get("is_operator", False)

    logger.info("=" * 60)
    logger.info("REQID GENERATOR NODE")
    logger.info("  current_message_id: %s", current_message_id)
    logger.info("  conversation_id: %s", conversation_id)
    logger.info("  customer_email: %s", customer_email)
    logger.info("  is_operator: %s", is_operator)
    logger.info("=" * 60)

    shipment = None

    # ── Step 1: Dedup check — is this message already processed? ──────────
    if current_message_id:
        shipment = await _safe_lookup(find_by_any_message_id, current_message_id)
        if shipment:
            logger.info("Step 1 HIT — message already processed (dedup): %s", current_message_id)
            return _hydrate_state(state, shipment)

    # ── Step 2: Check if In-Reply-To matches last_message_id ─
    if conversation_id:
        shipment = await _safe_lookup(find_by_last_message_id, conversation_id)
        if shipment:
            logger.info("Step 2 HIT — matched by last_message_id (In-Reply-To): %s", conversation_id)
            await update_shipment_thread_id(
                shipment.request_id, 
                current_message_id, 
                body=state.get("body", ""),
                translated_body=state.get("translated_body", ""),
                translated_subject=state.get("translated_subject", ""),
                attachments=state.get("attachments"),
                new_message=_build_message(state).model_dump()
            )
            return _hydrate_state(state, shipment)

    # ── Step 3: Check if In-Reply-To exists in message_ids array ──────────
    if conversation_id:
        shipment = await _safe_lookup(find_by_any_message_id, conversation_id)
        if shipment:
            logger.info("Step 3 HIT — matched message in conversation (message_ids): %s", conversation_id)
            await update_shipment_thread_id(
                shipment.request_id, 
                current_message_id, 
                body=state.get("body", ""),
                translated_body=state.get("translated_body", ""),
                translated_subject=state.get("translated_subject", ""),
                attachments=state.get("attachments"),
                new_message=_build_message(state).model_dump()
            )
            return _hydrate_state(state, shipment)

    # ── Step 4: Lookup by request_id (extracted from email body) ──────────
    if request_id:
        shipment = await _safe_lookup(find_by_request_id, request_id)
        if shipment:
            logger.info("Step 4 HIT — matched by request_id: %s", request_id)
            await update_shipment_thread_id(
                shipment.request_id, 
                current_message_id, 
                body=state.get("body", ""),
                translated_body=state.get("translated_body", ""),
                translated_subject=state.get("translated_subject", ""),
                attachments=state.get("attachments"),
                new_message=_build_message(state).model_dump()
            )
            return _hydrate_state(state, shipment)

    # ── Step 5: Lookup by email + open status ─────────────────────────────
    if customer_email:
        shipment = await _safe_lookup(find_by_email_and_open_status, customer_email)
        if shipment:
            logger.info("Step 5 HIT — matched by email %s with status %s", customer_email, shipment.status)
            await update_shipment_thread_id(
                shipment.request_id, 
                current_message_id, 
                body=state.get("body", ""),
                translated_body=state.get("translated_body", ""),
                translated_subject=state.get("translated_subject", ""),
                attachments=state.get("attachments"),
                new_message=_build_message(state).model_dump()
            )
            return _hydrate_state(state, shipment)

    # ── Step 6: Generate fresh request_id and store new shipment ──────────
    new_id = generate_request_id()
    state["request_id"] = new_id
    state["status"]     = "NEW"
    
    new_shipment = Shipment(
        request_id=new_id,
        thread_id=current_message_id,  # Set conversation root (NEVER changes)
        last_message_id=current_message_id,  # Set latest message (always updated)
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
        messages=[_build_message(state)]
    )
    await create_shipment(new_shipment)
    
    logger.info("Step 6 — generated and stored new request_id: %s", new_id)
    return state


def _build_message(state: AgentState):
    """Helper to build Message object from state."""
    from models.shipment import Message
    return Message(
        message_id=state.get("thread_id", ""),
        sender_email=state.get("customer_email", ""),
        sender_type="customer",
        direction="incoming",
        subject=state.get("subject"),
        body=state.get("body", ""),
        attachments=state.get("attachments", [])
    )

