import asyncio
import concurrent.futures
import logging
from datetime import datetime

from agent.state import AgentState
from api.shipment_service import update_shipment_data, push_message_log
from config import settings
from core.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import Message
from services.email_sender import send_email
from utils.email_template import build_email


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# LANGGRAPH NODE
# ─────────────────────────────────────────────────────────────

async def missing_info_node(state: AgentState) -> dict:
    """
    Runs when validation_node reports missing required fields.

    Steps:
      1. Validate required state fields  (raises ValueError if missing)
      2. Guard: skip if already MISSING_INFO  (duplicate processing)
      3. Update DB with node-produced data    (raises on failure)
      4. Build and send missing-info email    (raises on failure)
      5. Push message log + status to DB      (raises on failure)
      6. Return updated state fields
    """

    # ── Step 1: Validate required state fields ────────────────
    customer_email = state.get("customer_email", "")
    if not customer_email:
        raise ValueError("[missing_info_node] customer_email is missing in state.")

    request_id = state.get("request_id", "")
    if not request_id:
        raise ValueError("[missing_info_node] request_id is missing in state.")

    validation = state.get("validation_result")
    if not validation:
        raise ValueError("[missing_info_node] validation_result is None in state.")

    missing_fields = validation.missing_fields or []
    if not missing_fields:
        raise ValueError("[missing_info_node] missing_fields is empty — node should not have run.")

    # ── Step 2: Duplicate processing guard ───────────────────
    if state.get("status") == "MISSING_INFO":
        logger.warning(
            "[missing_info_node] request_id=%s already MISSING_INFO — skipping duplicate send.",
            request_id
        )
        return {}

    # ── Local variables ───────────────────────────────────────
    subject       = state.get("subject") or "Your Shipment Request"
    request_data  = state.get("request_data", {})
    customer_name = request_data.get("customer_name") or "Customer"

    # ── Step 3: Update DB before sending email ────────────────
    state_with_status = dict(state)
    state_with_status["status"] = "MISSING_INFO"

    try:
        await update_shipment_data(state_with_status)
    except Exception as e:
        logger.error(
            "[missing_info_node] DB pre-update failed for request_id=%s: %s",
            request_id, e, exc_info=True
        )
        raise RuntimeError(f"DB pre-update failed for request_id={request_id}") from e

    # ── Step 4: Build email ───────────────────────────────────
    body_html = build_email(
        email_type     = "missing_info",
        customer_name  = customer_name,
        request_id     = request_id,
        request_data   = request_data,
        missing_fields = missing_fields,
        all_fields     = REQUIRED_FIELDS + OPTIONAL_FIELDS,
    )
    email_subject = f"Re: {subject} — Additional Information Required"

    # ── Step 5: Send email ────────────────────────────────────
    try:
        sent_message_id = send_email(
            to         = customer_email,
            subject    = email_subject,
            body_html  = body_html,
            request_id = request_id
        )
    except RuntimeError as e:
        logger.error(
            "[missing_info_node] Email send failed for request_id=%s: %s",
            request_id, e, exc_info=True
        )
        raise RuntimeError(f"Email send failed for request_id={request_id}") from e

    # ── Step 6: Build Message log object ──────────────────────
    message_log = Message(
        message_id   = sent_message_id,
        sender_email = settings.GMAIL_ADDRESS,
        sender_type  = "system",
        direction    = "outgoing",
        subject      = email_subject,
        body         = f"Missing fields: {', '.join(missing_fields)}",
        received_at  = datetime.utcnow()
    )

    # ── Step 7: Push message log + update status in DB ────────
    try:
        await push_message_log(
            request_id      = request_id,
            message         = message_log.model_dump(),
            sent_message_id = sent_message_id,
            status          = "MISSING_INFO"
        )
    except Exception as e:
        logger.error(
            "[missing_info_node] DB message log push failed for request_id=%s: %s. "
            "Email WAS sent (ID: %s) but DB record is missing.",
            request_id, e, sent_message_id, exc_info=True
        )
        raise RuntimeError(
            f"DB push failed after email sent. Email ID: {sent_message_id}"
        ) from e

    # ── Step 8: Update state ──────────────────────────────────
    existing_message_ids = list(state.get("message_ids", []))
    existing_messages    = list(state.get("messages", []))

    logger.info(
        "[missing_info_node] Email sent | to=%s | request_id=%s | message_id=%s | missing=%s",
        customer_email, request_id, sent_message_id, missing_fields
    )

    return {
        "status":          "MISSING_INFO",
        "last_message_id": sent_message_id,
        "message_ids":     existing_message_ids + [sent_message_id],
        "messages":        existing_messages + [message_log],
    }
