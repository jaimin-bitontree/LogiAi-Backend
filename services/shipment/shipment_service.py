from datetime import datetime
import logging
from typing import Optional, List

from db.client import get_db
from models.shipment import Shipment

logger = logging.getLogger(__name__)

# Statuses that mean a shipment is still active / awaiting a reply
OPEN_STATUSES = ["MISSING_INFO", "PRICING_PENDING", "QUOTED"]


# ============================================================
# LOOKUP FUNCTIONS
# ============================================================

async def find_by_thread_id(thread_id: str):
    """Lookup shipment by thread_id (conversation root)."""
    db = get_db()
    doc = await db.shipments.find_one({"thread_id": thread_id})
    return Shipment(**doc) if doc else None


async def find_by_any_message_id(message_id: str):
    """Find shipment where message_id exists in message_ids array.
    This is used to match replies to any message in the conversation.
    """
    db = get_db()
    doc = await db.shipments.find_one({"message_ids": message_id})
    return Shipment(**doc) if doc else None


async def find_by_last_message_id(last_message_id: str):
    """Lookup shipment by last_message_id field."""
    db = get_db()
    doc = await db.shipments.find_one({"last_message_id": last_message_id})
    return Shipment(**doc) if doc else None


async def find_by_request_id(request_id: str):
    """Lookup shipment by request_id field."""
    db = get_db()
    doc = await db.shipments.find_one({"request_id": request_id})
    return Shipment(**doc) if doc else None


async def find_by_email_and_open_status(customer_email: str):
    """Find the most recent open shipment for a customer email.
    Open means status is one of MISSING_INFO, PRICING_PENDING, or QUOTED.
    """
    db = get_db()
    doc = await db.shipments.find_one(
        {"customer_email": customer_email, "status": {"$in": OPEN_STATUSES}},
        sort=[("created_at", -1)],
    )
    return Shipment(**doc) if doc else None


async def find_latest_by_email(customer_email: str):
    """Find the most recent shipment for a given customer email."""
    db = get_db()
    doc = await db.shipments.find_one(
        {"customer_email": customer_email},
        sort=[("created_at", -1)]
    )
    return Shipment(**doc) if doc else None


async def message_id_already_processed(message_id: str) -> bool:
    """Return True if this Gmail Message-ID is already stored in any shipment."""
    db = get_db()
    doc = await db.shipments.find_one({"message_ids": message_id})
    return doc is not None


# ============================================================
# CREATE FUNCTIONS
# ============================================================

async def create_shipment(shipment: Shipment):
    """Create a new shipment document in MongoDB."""
    db = get_db()
    await db.shipments.insert_one(shipment.dict())


# ============================================================
# UPDATE FUNCTIONS
# ============================================================

async def update_shipment(request_id: str, updates: dict) -> None:
    """
    Generic update function for shipment documents.
    
    Updates any fields on an existing shipment by request_id.
    Automatically adds updated_at timestamp.

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


async def update_shipment_thread_id(
    request_id: str, 
    new_thread_id: str, 
    body: str = None,
    translated_body: str = None,
    translated_subject: str = None,
    attachments: List = None, 
    new_message: dict = None
):
    """Update shipment by adding a new message_id, updating thread pointers, appending attachments and messages.
    Merges new body content with existing body to maintain full conversation context."""
    db = get_db()
    
    # Fetch existing shipment to get current body
    existing_shipment = await db.shipments.find_one({"request_id": request_id})
    
    update_ops = {
        "$addToSet": {"message_ids": new_thread_id},
        "$set": {
            "thread_id": new_thread_id,
            "last_message_id": new_thread_id,
            "updated_at": datetime.utcnow()
        },
    }

    # Merge body: append new body to existing body with separator
    if body and existing_shipment:
        existing_body = existing_shipment.get("body", "")
        if existing_body:
            merged_body = f"{existing_body}\n\n--- Customer Reply ---\n\n{body}"
        else:
            merged_body = body
        update_ops["$set"]["body"] = merged_body
    elif body:
        update_ops["$set"]["body"] = body
    
    # Merge translated_body: append new translated body to existing
    if translated_body and existing_shipment:
        existing_translated = existing_shipment.get("translated_body", "")
        if existing_translated:
            merged_translated = f"{existing_translated}\n\n--- Customer Reply ---\n\n{translated_body}"
        else:
            merged_translated = translated_body
        update_ops["$set"]["translated_body"] = merged_translated
    elif translated_body:
        update_ops["$set"]["translated_body"] = translated_body
    
    if translated_subject:
        update_ops["$set"]["translated_subject"] = translated_subject

    if attachments:
        # Convert Pydantic models to dict if they aren't already
        attachment_dicts = [a.dict() if hasattr(a, "dict") else a for a in attachments]
        update_ops["$push"] = {"attachments": {"$each": attachment_dicts}}
    
    if new_message:
        if "$push" not in update_ops:
            update_ops["$push"] = {}
        update_ops["$push"]["messages"] = new_message

    await db.shipments.update_one({"request_id": request_id}, update_ops)


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


async def push_pricing_details(request_id: str, pricing_data: dict) -> None:
    """
    Append pricing data to the pricing_details array for a shipment.
    
    Args:
        request_id: The shipment's request_id to match.
        pricing_data: Serialized PricingSchema dict to append.
    """
    db = get_db()
    
    result = await db["shipments"].update_one(
        {"request_id": request_id},
        {
            "$push": {"pricing_details": pricing_data},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    
    if result.matched_count == 0:
        logger.warning(f"No shipment found with request_id={request_id}")
    else:
        logger.info(f"Pricing details pushed | request_id: {request_id}")


async def set_pricing_details(request_id: str, pricing_data: dict) -> None:
    """
    Replace entire pricing_details array with single merged pricing object.
    Used for operator pricing updates to merge instead of append.
    
    Args:
        request_id: The shipment's request_id to match.
        pricing_data: Serialized PricingSchema dict to set (replaces entire array).
    """
    db = get_db()
    
    result = await db["shipments"].update_one(
        {"request_id": request_id},
        {
            "$set": {
                "pricing_details": [pricing_data],
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    if result.matched_count == 0:
        logger.warning(f"No shipment found with request_id={request_id}")
    else:
        logger.info(f"Pricing details set (replaced) | request_id: {request_id}")


# ============================================================
# FETCH FUNCTIONS
# ============================================================

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
                "_id":                 0, 
                "language_metadata":   1,  # needed for multi-language email responses
                "pricing_details":     1,
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


async def list_shipments(
    status: Optional[str] = None
) -> List[Shipment]:
    """
    Fetch all shipments with optional status filtering.
    Ordered by creation date (newest first).
    """
    db = get_db()
    query = {}
    
    if status:
        query["status"] = status
    
    cursor = db.shipments.find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=None)
    
    return [Shipment(**doc) for doc in docs]


# ============================================================
# MESSAGE LOG HELPER
# ============================================================

async def log_outgoing_message(
    request_id:  str,
    message_id:  str,
    subject:     str,
    body:        str,
    status:      str,
    sender_type: str = "system",
):
    """
    Build a Message object for an outgoing email and push it to the DB log.

    Args:
        request_id:  Shipment request ID
        message_id:  Sent email Message-ID
        subject:     Email subject
        body:        Short description / body summary for the log
        status:      Shipment status to set after logging
        sender_type: Defaults to "system"
    """
    from datetime import datetime
    from config.settings import settings
    from models.shipment import Message

    msg = Message(
        message_id   = message_id,
        sender_email = settings.GMAIL_ADDRESS,
        sender_type  = sender_type,
        direction    = "outgoing",
        subject      = subject,
        body         = body,
        received_at  = datetime.utcnow(),
    )
    await push_message_log(
        request_id      = request_id,
        message         = msg.model_dump(),
        sent_message_id = message_id,
        status          = status,
    )
    logger.debug("[shipment_service] Logged | request_id=%s | msg_id=%s | status=%s", request_id, message_id, status)