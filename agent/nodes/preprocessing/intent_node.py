import logging
from agent.state import AgentState
from models.shipment import IntentResult
from services.ai.intent_service import detect_intent

logger = logging.getLogger(__name__)


# ===================================================
# LANGGRAPH NODE
# ===================================================

def intent_node(state: AgentState) -> dict:
    """
    Reads translated_subject and translated_body from state.
    Returns intent and optionally request_id (only if found in email).
    """
    result = detect_intent(
        state.get("translated_subject", ""),
        state.get("translated_body", ""),
    )

    _log_intent_result(state.get("translated_subject", ""), result)

    # Only update request_id if one was found in the email AND state doesn't have one yet
    update = {"intent": result.intent.value}
    
    if result.request_id and not state.get("request_id"):
        update["request_id"] = result.request_id

    return update


# ===================================================
# CONSOLE PRINT HELPER
# ===================================================

def _log_intent_result(subject: str, result: IntentResult) -> None:
    logger.info("=" * 60)
    logger.info("[intent_node] RESULT")
    logger.info(f"Subject    : {subject.strip() or '(no subject)'}")
    logger.info(f"Intent     : {result.intent.value}")
    logger.info(f"Request ID : {result.request_id or 'NOT FOUND'}")
    logger.info("=" * 60)
