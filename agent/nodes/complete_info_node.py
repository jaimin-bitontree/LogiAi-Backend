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

async def complete_info_node(state: AgentState) -> dict:
    """
    Runs when validation_node reports all required fields are present.

    Steps:
      1. Validate required state fields
      2. Update DB with all node-produced data + status=PRICING_PENDING
      3. Send confirmation email to customer
         → push to message_ids + messages (last_message_id NOT updated)
      4. Send notification email to operator (all extracted fields)
         → push to message_ids + messages + set last_message_id
            (operator's reply will be matched via this ID)
      5. Return updated state
    """

    # ── Step 1: Guard — required state fields ────────────────
    customer_email = state.get("customer_email", "")
    if not customer_email:
        raise ValueError("[complete_info_node] customer_email is missing in state.")

    request_id = state.get("request_id", "")
    if not request_id:
        raise ValueError("[complete_info_node] request_id is missing in state.")

    operator_email = settings.OPERATOR_EMAIL
    if not operator_email:
        raise ValueError("[complete_info_node] OPERATOR_EMAIL is not configured in settings.")

    # ── Step 2: Update DB with node-produced data ─────────────
    state_with_status = dict(state)
    state_with_status["status"] = "PRICING_PENDING"

    try:
        await update_shipment_data(state_with_status)
    except Exception as e:
        logger.error(
            "[complete_info_node] DB pre-update failed for request_id=%s: %s",
            request_id, e, exc_info=True
        )
        raise RuntimeError(f"DB pre-update failed for request_id={request_id}") from e

    # ── Local variables ───────────────────────────────────────
    subject       = state.get("subject") or "Your Shipment Request"
    request_data  = state.get("request_data", {})
    customer_name = request_data.get("customer_name") or "Customer"
    all_fields    = REQUIRED_FIELDS + OPTIONAL_FIELDS

    # ── Step 3: Send customer confirmation email ──────────────
    customer_html = build_email(
        email_type    = "status",
        customer_name = customer_name,
        request_id    = request_id,
        request_data  = request_data,
        all_fields    = all_fields,
        status        = "PRICING_PENDING",
        message       = (
            "We have received all the information needed for your shipment request. "
            "Our team is reviewing the details and you will receive a quotation shortly."
        ),
        next_steps    = [
            "Our team will review your request thoroughly",
            "We will prepare a detailed pricing proposal",
            "You will receive our response shortly"
        ]
    )
    customer_subject = f"Re: {subject} — Request Received ✅"

    try:
        customer_msg_id = send_email(
            to         = customer_email,
            subject    = customer_subject,
            body_html  = customer_html,
            request_id = request_id
        )
    except RuntimeError as e:
        logger.error(
            "[complete_info_node] Customer email send failed for request_id=%s: %s",
            request_id, e, exc_info=True
        )
        raise RuntimeError(f"Customer email send failed for request_id={request_id}") from e

    # Build customer message log
    customer_message_log = Message(
        message_id   = customer_msg_id,
        sender_email = settings.GMAIL_ADDRESS,
        sender_type  = "system",
        direction    = "outgoing",
        subject      = customer_subject,
        body         = "Confirmation sent to customer — all fields received.",
        received_at  = datetime.utcnow()
    )

    # Push to DB — last_message_id NOT updated (customer email)
    try:
        await push_message_log(
            request_id             = request_id,
            message                = customer_message_log.model_dump(),
            sent_message_id        = customer_msg_id,
            status                 = "PRICING_PENDING",
        )
    except Exception as e:
        logger.error(
            "[complete_info_node] DB push failed for customer log request_id=%s: %s",
            request_id, e, exc_info=True
        )
        raise RuntimeError(f"DB push failed for customer log, request_id={request_id}") from e

    # ── Step 4: Send operator notification email ──────────────
    operator_html = build_email(
        email_type    = "pricing",         # shows all extracted fields (no price yet)
        customer_name = "Operator",        # address it to the Operator
        request_id    = request_id,
        request_data  = request_data,
        all_fields    = all_fields,
        pricing       = None,              # empty — operator needs to fill price
    )
    operator_subject = f"New Shipment Request — {request_id}"

    try:
        operator_msg_id = send_email(
            to         = operator_email,
            subject    = operator_subject,
            body_html  = operator_html,
            request_id = request_id
        )
    except RuntimeError as e:
        logger.error(
            "[complete_info_node] Operator email send failed for request_id=%s: %s",
            request_id, e, exc_info=True
        )
        raise RuntimeError(f"Operator email send failed for request_id={request_id}") from e

    # Build operator message log
    operator_message_log = Message(
        message_id   = operator_msg_id,
        sender_email = settings.GMAIL_ADDRESS,
        sender_type  = "system",
        direction    = "outgoing",
        subject      = operator_subject,
        body         = "Operator notified — awaiting pricing reply.",
        received_at  = datetime.utcnow()
    )

    # Push to DB — last_message_id IS updated to operator's message ID
    # So when operator replies, reqid_generator_node can match
    # their reply (In-Reply-To: operator_msg_id) → find this shipment
    try:
        await push_message_log(
            request_id             = request_id,
            message                = operator_message_log.model_dump(),
            sent_message_id        = operator_msg_id,
            status                 = "PRICING_PENDING",
        )
    except Exception as e:
        logger.error(
            "[complete_info_node] DB push failed for operator log request_id=%s: %s. "
            "Operator email WAS sent (ID: %s) but DB record is missing.",
            request_id, e, operator_msg_id, exc_info=True
        )
        raise RuntimeError(f"DB push failed for operator log, request_id={request_id}") from e

    # ── Step 5: Update state ──────────────────────────────────
    existing_message_ids = list(state.get("message_ids", []))
    existing_messages    = list(state.get("messages", []))

    logger.info(
        "[complete_info_node] Done | request_id=%s | customer_msg=%s | operator_msg=%s",
        request_id, customer_msg_id, operator_msg_id
    )

    return {
        "status":          "PRICING_PENDING",
        "last_message_id": operator_msg_id,            # operator's ID — for reply matching
        "message_ids":     existing_message_ids + [customer_msg_id, operator_msg_id],
        "messages":        existing_messages + [customer_message_log, operator_message_log],
    }
