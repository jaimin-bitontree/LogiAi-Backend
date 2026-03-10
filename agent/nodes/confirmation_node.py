import logging
from datetime import datetime
from agent.state import AgentState
from api.shipment_service import update_shipment_data, push_message_log
from config import settings
from core.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import Message
from services.email_sender import send_email
from utils.email_template import build_email
from db.client import get_db

logger = logging.getLogger(__name__)

# LANGGRAPH NODE


async def confirmation_node(state: AgentState) -> dict:
    """
    Runs when intent = "confirmation".

    Steps:
      1. Read conversation_id (In-Reply-To) from state
      2. Fetch shipment from DB using last_message_id == conversation_id
      3. Check status == "QUOTED" -- if not, skip silently
      4. Send notification email to operator
         -> push log 1 to DB
      5. Update DB status -> "CONFIRMED"
      6. Send thank-you email to customer
         -> push log 2 to DB
      7. Push incoming customer confirmation as log 3 to DB
      8. Return updated state
    """

    # Step 1: Read conversation_id from state
    conversation_id = state.get("conversation_id")
    if not conversation_id:
        logger.warning("[confirmation_node] No conversation_id in state -- skipping.")
        return {}

    # Step 2: Fetch shipment from DB

    db = get_db()
    try:
        shipment = await db.shipments.find_one({"last_message_id": conversation_id})
    except Exception as e:
        logger.error(
            "[confirmation_node] DB lookup failed for last_message_id=%s: %s",
            conversation_id, e, exc_info=True
        )
        raise RuntimeError(f"DB lookup failed for last_message_id={conversation_id}") from e

    if not shipment:
        logger.warning(
            "[confirmation_node] No shipment found for last_message_id=%s -- skipping.",
            conversation_id
        )
    return {}

    request_id     = shipment.get("request_id", "")
    current_status = shipment.get("status", "")
    request_data   = shipment.get("request_data", {})
    customer_email = shipment.get("customer_email", "")
    subject        = shipment.get("subject") or "Your Shipment"

    logger.info(
        "[confirmation_node] Found shipment | request_id=%s | status=%s",
        request_id, current_status
    )

    # Local variables
    operator_email = settings.OPERATOR_EMAIL
    all_fields = REQUIRED_FIELDS + OPTIONAL_FIELDS
    customer_name = (
        request_data.get("required", {}).get("customer_name")
        or request_data.get("customer_name")
        or "Customer"
    )

    # Step 3: Check status
    if current_status == "PRICING_PENDING":
        logger.info(
            "[confirmation_node] Status is PRICING_PENDING -- sending pricing reminder to operator | request_id=%s",
            request_id
        )

        reminder_html = build_email(
            email_type="pricing",
            customer_name="Operator",
            request_id=request_id,
            request_data=request_data,
            all_fields=all_fields,
            pricing_details=[],
        )
        reminder_subject = f"[REMINDER] Pricing Required -- {request_id}"

        try:
            reminder_msg_id = send_email(
                to=operator_email,
                subject=reminder_subject,
                body_html=reminder_html,
                request_id=request_id
            )
        except RuntimeError as e:
            logger.error(
                "[confirmation_node] Operator reminder email failed for request_id=%s: %s",
                request_id, e, exc_info=True
            )
            raise RuntimeError(f"Operator reminder email failed for request_id={request_id}") from e

        reminder_log = Message(
            message_id=reminder_msg_id,
            sender_email=settings.GMAIL_ADDRESS,
            sender_type="system",
            direction="outgoing",
            subject=reminder_subject,
            body="Pricing reminder sent to operator.",
            received_at=datetime.utcnow()
        )

        try:
            await push_message_log(
                request_id=request_id,
                message=reminder_log.model_dump(),
                sent_message_id=reminder_msg_id,
                status="PRICING_PENDING",
            )
        except Exception as e:
            logger.error(
                "[confirmation_node] DB push failed for reminder log request_id=%s: %s",
                request_id, e, exc_info=True
            )
            raise RuntimeError(f"DB push failed for reminder log, request_id={request_id}") from e

        logger.info(
            "[confirmation_node] Pricing reminder sent | request_id=%s | msg_id=%s",
            request_id, reminder_msg_id
        )

        existing_message_ids = list(state.get("message_ids", []))
        existing_messages = list(state.get("messages", []))

        return {
            "status":      "PRICING_PENDING",
            "request_id":  request_id,
            "message_ids": existing_message_ids + [reminder_msg_id],
            "messages":    existing_messages + [reminder_log],
        }

    if current_status != "QUOTED":
        logger.warning(
            "[confirmation_node] Status is '%s', expected 'QUOTED' -- skipping.",
            current_status
        )
        return {}

    # Step 4: incoming customer confirmation email
    incoming_msg_id = state.get("message_id") or conversation_id
    incoming_body = state.get("body") or "Customer confirmed the shipment."

    customer_confirmation_log = Message(
        message_id=incoming_msg_id,
        sender_email=customer_email,
        sender_type="customer",
        direction="incoming",
        subject=state.get("subject") or subject,
        body=incoming_body,
        received_at=datetime.utcnow()
    )

    try:
        await push_message_log(
            request_id=request_id,
            message=customer_confirmation_log.model_dump(),
            sent_message_id=incoming_msg_id,
            status="CONFIRMED",
        )
    except Exception as e:
        logger.error(
            "[confirmation_node] DB push failed for incoming log request_id=%s: %s",
            request_id, e, exc_info=True
        )
        raise RuntimeError(f"DB push failed for incoming log, request_id={request_id}") from e

    # Step 5: Send notification email to operator
    operator_html = build_email(
        email_type="status",
        customer_name="Operator",
        request_id=request_id,
        request_data=request_data,
        all_fields=all_fields,
        status="CONFIRMED",
        message=(
            f"The customer ({customer_name}) has confirmed the shipment. "
            "Please proceed with the logistics arrangements."
        ),
    )
    operator_subject = f"Customer Confirmed Shipment -- {request_id}"

    try:
        operator_msg_id = send_email(
            to=operator_email,
            subject=operator_subject,
            body_html=operator_html,
            request_id=request_id
        )
    except RuntimeError as e:
        logger.error(
            "[confirmation_node] Operator email send failed for request_id=%s: %s",
            request_id, e, exc_info=True
        )
        raise RuntimeError(f"Operator email send failed for request_id={request_id}") from e

    # operator notification
    operator_message_log = Message(
        message_id=operator_msg_id,
        sender_email=settings.GMAIL_ADDRESS,
        sender_type="system",
        direction="outgoing",
        subject=operator_subject,
        body="Operator notified -- customer confirmed the shipment.",
        received_at=datetime.utcnow()
    )

    try:
        await push_message_log(
            request_id=request_id,
            message=operator_message_log.model_dump(),
            sent_message_id=operator_msg_id,
            status="CONFIRMED",
        )
    except Exception as e:
        logger.error(
            "[confirmation_node] DB push failed for operator log request_id=%s: %s",
            request_id, e, exc_info=True
        )
        raise RuntimeError(f"DB push failed for operator log, request_id={request_id}") from e

    # Step 6: Update DB status -> CONFIRMED
    try:
        await update_shipment_data({
            "request_id": request_id,
            "status":     "CONFIRMED",
        })
    except Exception as e:
        logger.error(
            "[confirmation_node] DB status update failed for request_id=%s: %s",
            request_id, e, exc_info=True
        )
        raise RuntimeError(f"DB status update failed for request_id={request_id}") from e

    # Step 7: Send thank-you email to customer
    customer_html = build_email(
        email_type="status",
        customer_name=customer_name,
        request_id=request_id,
        request_data=request_data,
        all_fields=all_fields,
        status="CONFIRMED",
        message=(
            "Thank you for confirming your shipment with LogiAI. "
            "We are delighted to have you on board and will handle your shipment "
            "with the utmost care and professionalism."
        ),
        next_steps=[
            "Our team will coordinate all logistics for your shipment",
            "You will receive regular updates on the shipment progress",
            "Feel free to contact us anytime with your Request ID for any queries",
        ]
    )
    customer_subject = f"Re: {subject} -- Shipment Confirmed"

    try:
        customer_msg_id = send_email(
            to=customer_email,
            subject=customer_subject,
            body_html=customer_html,
            request_id=request_id
        )
    except RuntimeError as e:
        logger.error(
            "[confirmation_node] Customer email send failed for request_id=%s: %s",
            request_id, e, exc_info=True
        )
        raise RuntimeError(f"Customer email send failed for request_id={request_id}") from e

    # customer thank-you
    customer_message_log = Message(
        message_id=customer_msg_id,
        sender_email=settings.GMAIL_ADDRESS,
        sender_type="system",
        direction="outgoing",
        subject=customer_subject,
        body="Thank-you email sent to customer -- shipment confirmed.",
        received_at=datetime.utcnow()
    )

    try:
        await push_message_log(
            request_id=request_id,
            message=customer_message_log.model_dump(),
            sent_message_id=customer_msg_id,
            status="CONFIRMED",
        )
    except Exception as e:
        logger.error(
            "[confirmation_node] DB push failed for customer log request_id=%s: %s",
            request_id, e, exc_info=True
        )
        raise RuntimeError(f"DB push failed for customer log, request_id={request_id}") from e

    logger.info(
        "[confirmation_node] Done | request_id=%s | status=CONFIRMED | "
        "incoming_msg=%s | operator_msg=%s | customer_msg=%s",
        request_id, incoming_msg_id, operator_msg_id, customer_msg_id
    )

    # Step 8: Return updated state
    existing_message_ids = list(state.get("message_ids", []))
    existing_messages = list(state.get("messages", []))

    return {
        "status":          "CONFIRMED",
        "request_id":      request_id,
        "last_message_id": operator_msg_id,
        "message_ids":     existing_message_ids + [incoming_msg_id, operator_msg_id, customer_msg_id],
        "messages":        existing_messages + [customer_confirmation_log, operator_message_log, customer_message_log],
    }
