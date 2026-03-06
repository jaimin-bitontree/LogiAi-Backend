from datetime import datetime

from db.client import get_db
from utils.serialization import serialize_pydantic



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

    updates = {
        # ── Language (language_node) ───────────────────────────
        "translated_body":    state.get("translated_body", ""),
        "translated_subject": state.get("translated_subject", ""),
        "language_metadata":  serialize_pydantic(state.get("language_metadata")),

        # ── Intent (intent_node) ──────────────────────────────
        "intent": state.get("intent"),

        # ── Extracted Fields (extract_node) ───────────────────
        "request_data": state.get("request_data", {}),

        # ── Validation (validation_node) ──────────────────────
        "validation_result": serialize_pydantic(state.get("validation_result")),

        # ── Status (missing_info_node) ────────────────────────
        "status": state.get("status", "NEW"),

        # ── Timestamp ─────────────────────────────────────────
        "updated_at": datetime.utcnow(),
    }

    result = await db["shipments"].update_one(
        {"request_id": request_id},
        {"$set": updates}
    )

    if result.matched_count == 0:
        print(f"⚠️  No shipment found with request_id={request_id}")
    else:
        print(f"✅ Shipment updated | request_id: {request_id}")


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
        print(f"⚠️  No shipment found with request_id={request_id}")
    else:
        print(f"✅ Message log pushed | request_id: {request_id} | message_id: {sent_message_id}")


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
        print(f"⚠️  No shipment found with request_id={request_id}")
    else:
        print(f"✅ Shipment updated | request_id: {request_id} | fields: {list(updates.keys())}")
