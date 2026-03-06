from agent.state import AgentState
from models.shipment import IntentResult
from services.intent_service import detect_intent


# ===================================================
# LANGGRAPH NODE
# ===================================================

def intent_node(state: AgentState) -> dict:
    """
    Reads translated_subject and translated_body from state.
    Returns only intent and request_id (if found).
    """
    result = detect_intent(
        state.get("translated_subject", ""),
        state.get("translated_body", ""),
    )

    _print_intent_result(state.get("translated_subject", ""), result)

    return {
        "intent": result.intent.value,
        "request_id": result.request_id or "",
    }


# ===================================================
# CONSOLE PRINT HELPER
# ===================================================

def _print_intent_result(subject: str, result: IntentResult) -> None:
    print("\n" + "=" * 60)
    print("[intent_node] RESULT")
    print(f"  Subject    : {subject.strip() or '(no subject)'}")
    print(f"  Intent     : {result.intent.value}")
    print(f"  Request ID : {result.request_id or 'NOT FOUND'}")
    print("=" * 60)
