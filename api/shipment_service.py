from datetime import datetime
import logging
from typing import Optional

from db.client import get_db
from utils.serialization import serialize_pydantic

logger = logging.getLogger(__name__)



async def update_shipment_data(state: dict) -> None:
    """
    Update an existing shipment document with fields produced by the agent nodes.

    The document is already created at request_id generation time with the
    core identity fields (request_id, customer_email, subject, body,
    attachments, message_ids, status, created_at).

    This function only patches the fields that are NEW after node processing:
      - translated_body / translated_subject  (language_node)
      - language_metadata                     (language_node)
      - intent                                (intent_node)
      - request_data                          (extract_node)
      - validation_result                     (validation_node)
      - status                                (missing_info_node)
    """
    db         = get_db()
    request_id = state.get("request_id", "")
    if not request_id:
        logger.error("[shipment_service] update_shipment_data failed: no request_id provided.")
        return

    # Build update dict dynamically mapping state keys to DB fields
    # Only include keys that are actually present in the 'state' input
    mapping = {
        "translated_body":    "translated_body",
        "translated_subject": "translated_subject",
        "language_metadata":  "language_metadata",
        "intent":             "intent",
        "request_data":       "request_data",
        "validation_result":  "validation_result",
        "status":             "status",
    }

    updates = {}
    for state_key, db_key in mapping.items():
        if state_key in state:
            val = state[state_key]
            # Handle serialization for Pydantic objects
            if state_key in ["language_metadata", "validation_result"]:
                val = serialize_pydantic(val)
            updates[db_key] = val

    if not updates:
        return

    updates["updated_at"] = datetime.utcnow()

    result = await db["shipments"].update_one(
        {"request_id": request_id},
        {"$set": updates}
    )

    if result.matched_count == 0:
        logger.warning(f"No shipment found with request_id={request_id}")
    else:
        logger.info(f"Shipment updated | request_id: {request_id}")


async def push_message_log(request_id: str, message: dict, sent_message_id: str, status: str = "MISSING_INFO") -> None:
    """
    After sending an email, atomically:
      - Append sent_message_id to message_ids array      ($push)
      - Append the message log object to messages array  ($push)
      - Set last_message_id to the sent_message_id       ($set)
      - Set status                                       ($set)
      - Set updated_at                                   ($set)

    Uses $push so existing array entries are NOT overwritten.

    Args:
        request_id:       The shipment's request_id to match.
        message:          Serialized Message dict to log the outgoing email.
        sent_message_id:  The Message-ID returned by email_sender.send_email().
        status:           New status to set after sending (default: MISSING_INFO).
    """
    db = get_db()

    result = await db["shipments"].update_one(
        {"request_id": request_id},
        {
            "$push": {
                "message_ids": sent_message_id,
                "messages":    message,
            },
            "$set": {
                "last_message_id": sent_message_id,
                "status":          status,
                "updated_at":      datetime.utcnow(),
            }
        }
    )

    if result.matched_count == 0:
        logger.warning(f"No shipment found with request_id={request_id}")
    else:
        logger.info(f"Message log pushed | request_id: {request_id} | message_id: {sent_message_id}")


async def update_shipment(request_id: str, updates: dict) -> None:
    """
    Generic patch: update specific fields on an existing shipment by request_id.

    Args:
        request_id: The shipment's request_id to match.
        updates:    Dict of fields to $set on the document.
    """
    db = get_db()
    updates["updated_at"] = datetime.utcnow()

    result = await db["shipments"].update_one(
        {"request_id": request_id},
        {"$set": updates}
    )

    if result.matched_count == 0:
        logger.warning(f"No shipment found with request_id={request_id}")
    else:
        logger.info(f"Shipment updated | request_id: {request_id} | fields: {list(updates.keys())}")


async def get_request_data(request_id: str) -> dict:
    """
    Fetch just the request_data field from the shipment document.
    Used by email tools to read extracted data without the LLM needing to pass it.

    Returns: request_data dict (has 'required' and 'optional' keys), or {}.
    """
    db  = get_db()
    doc = await db["shipments"].find_one(
        {"request_id": request_id},
        {"request_data": 1, "_id": 0}
    )
    return doc.get("request_data", {}) if doc else {}

async def get_shipment_by_request_id(request_id: str) -> Optional[dict]:
    """
    Fetch a single shipment document from MongoDB by request_id.

    Used by extraction tools to read email body and existing data
    without passing large strings through the LLM tool calls.

    Args:
        request_id: The REQ-ID string e.g. REQ-2026-0309075733293729

    Returns:
        Shipment dict if found, None if not found.
    """
    db = get_db()
    try:
        shipment = await db["shipments"].find_one(
            {"request_id": request_id},
            {
                # Only fetch fields we actually need
                # Avoids loading entire document unnecessarily
                "request_id":          1,
                "subject":             1,
                "translated_subject":  1,
                "body":                1,
                "translated_body":     1,
                "request_data":        1,
                "validation_result":   1,
                "status":              1,
                "customer_email":      1,
                "last_message_id":     1,
                "_id":                 0,   # never return _id
            }
        )

        if not shipment:
            logger.warning("[shipment_service] Not found: %s", request_id)
            return None

        logger.info("[shipment_service] Found: %s", request_id)
        return shipment

    except Exception as e:
        logger.error("[shipment_service] get_shipment_by_request_id failed: %s | error: %s", request_id, e)
        return None