"""
agent/tools/db_tools.py

LangChain tools for database operations.
The LLM calls these tools to persist data after processing.
"""

import logging
from langchain_core.tools import tool
from api.shipment_service import push_message_log, update_shipment_data

logger = logging.getLogger(__name__)


@tool
async def log_outgoing_message(
    request_id:      str,
    message:         dict,
    sent_message_id: str,
    status:          str,
) -> str:
    """
    Saves an outgoing system email to the shipment's message log in the database.
    Also updates the shipment's status and last_message_id in MongoDB.

    ALWAYS call this tool after send_missing_info_email or send_complete_info_emails
    to ensure the database stays consistent.

    Args:
        request_id: The shipment request ID to update
        message: The message log dict (from the tool return value)
        sent_message_id: The Message-ID of the sent email
        status: The new shipment status (e.g. MISSING_INFO, PRICING_PENDING)

    Returns: Confirmation string.
    """
    await push_message_log(
        request_id      = request_id,
        message         = message,
        sent_message_id = sent_message_id,
        status          = status,
    )
    logger.info("[db_tools] Logged message %s for request %s (status=%s)", sent_message_id, request_id, status)
    return f"✅ Logged {sent_message_id} for {request_id} — status set to {status}"


@tool
async def save_shipment_data(state_snapshot: dict) -> str:
    """
    Persists the current shipment state (extracted fields, intent, translated body,
    validation result, status) to the MongoDB shipments collection.

    Call this after extraction is done and before sending any email, to ensure
    the data is saved even if email sending fails.

    Args:
        state_snapshot: A dict containing the current state fields to persist.

    Returns: Confirmation string.
    """
    await update_shipment_data(state_snapshot)
    request_id = state_snapshot.get("request_id", "unknown")
    logger.info("[db_tools] Saved shipment data for %s", request_id)
    return f"✅ Saved shipment data for {request_id}"
