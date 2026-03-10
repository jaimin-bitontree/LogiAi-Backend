from langgraph.graph import StateGraph, START, END
from agent.state import AgentState
from agent.nodes.parse_node import parser_node
from agent.nodes.language_node import language_node
from agent.nodes.intent_node import intent_node
from agent.nodes.extraction_node import extraction_node
from agent.nodes.missing_info_node import missing_info_node
from agent.nodes.complete_info_node import complete_info_node
from agent.nodes.reqid_generator_node import generate_reqid
from agent.nodes.confirmation_node import confirmation_node
from agent.nodes.status_node import status_handler
from agent.nodes.cancellation_node import cancellation_handler
from agent.nodes.pricing_node import pricing_node
from models.shipment import LanguageMetadata, ValidationResult, Attachment
from core.constants import EmailIntent

builder = StateGraph(AgentState)

# ── Nodes ─────────────────────────────────────────────────────
builder.add_node("parser",        parser_node)
builder.add_node("language",      language_node)
builder.add_node("intent",        intent_node)
builder.add_node("reqid",         generate_reqid)
builder.add_node("extraction",    extraction_node)
builder.add_node("missing_info",  missing_info_node)
builder.add_node("complete_info", complete_info_node)
builder.add_node("confirmation",  confirmation_node)
builder.add_node("status",        status_handler)
builder.add_node("cancellation",  cancellation_handler)
builder.add_node("pricing",       pricing_node)

# ── Routers ────────────────────────────────────────────────────
def route_after_parser(state: AgentState):
    """Route after parse_node - all emails go to language node."""
    if state.get("is_operator") and state.get("shipment_found"):
        return "language"  # Operator email with valid request_id → language
    elif state.get("is_operator"):
        return "error"  # Operator email but no request_id found → error
    return "language"  # Customer email → language first

def route_after_intent(state: AgentState):
    """Route after intent_node based on intent and sender type."""
    intent = state.get("intent")
    is_operator = state.get("is_operator", False)
    
    # If operator email with pricing intent, go to pricing node
    if is_operator and intent == "operator_pricing":
        return "pricing"
    
    # Route based on customer intent
    if intent == "status_inquiry":
        return "status"
    elif intent == "cancellation":
        return "cancellation"
    elif intent == "confirmation":
        return "confirmation"
    elif intent in ["new_request", "missing_information"]:
        return "reqid"
    else:
        return END

def route_after_reqid(state: AgentState):
    """Route after reqid_generator_node for customer emails."""
    return "extraction"

def route_after_extraction(state: AgentState):
    """Route based on whether all required fields were found."""
    val_res = state.get("validation_result")
    status = state.get("status")

    if status == "ERROR":
        return END
    
    if not val_res:
        return END

    if val_res.is_valid:
        return "complete_info"
    elif val_res.missing_fields:
        return "missing_info"
    
    return END

# ── Edges ─────────────────────────────────────────────────────
builder.add_edge(START, "parser")

builder.add_conditional_edges(
    "parser",
    route_after_parser,
    {
        "language": "language",
        "error": END
    }
)

builder.add_edge("language", "intent")

builder.add_conditional_edges(
    "intent",
    route_after_intent,
    {
        "pricing": "pricing",
        "status": "status",
        "cancellation": "cancellation",
        "confirmation": "confirmation",
        "reqid": "reqid",
        END: END
    }
)

builder.add_conditional_edges(
    "reqid",
    route_after_reqid,
    {
        "extraction": "extraction"
    }
)


builder.add_conditional_edges(
    "extraction",
    route_after_extraction,
    {
        "complete_info": "complete_info",
        "missing_info": "missing_info",
        END: END
    }
)

# Terminal Edges
builder.add_edge("pricing",       END)
builder.add_edge("status",        END)
builder.add_edge("cancellation",  END)
builder.add_edge("confirmation",  END)
builder.add_edge("missing_info",  END)
builder.add_edge("complete_info", END)
builder.add_edge("confirmation",  END)

graph = builder.compile()

# ── Helpers ────────────────────────────────────────────────────

def create_initial_state(raw_email: bytes) -> AgentState:
    return {
        "raw_email": raw_email,
        "request_id":         "",
        "thread_id":          None,
        "conversation_id":    None,
        "last_message_id":    None,
        "customer_email":     "",
        "subject":            None,
        "message_ids":        [],         
        "body":               "",
        "translated_body":    "",
        "translated_subject": "",
        "status":             "NEW",  
        "intent":             None,   
        "attachments":        [],
        "language_metadata":  LanguageMetadata(),
        "request_data":       {},
        "validation_result":  ValidationResult(),
        "pricing_details":    [],
        "messages":           [],
        "is_operator":        False,
        "shipment_found":     False,
        "final_document":     None,
    }


async def run_workflow(raw_email: bytes) -> AgentState:
    """
    Create initial state and invoke graph using astream (async).
    """
    try:
        initial_state = create_initial_state(raw_email)
        final_state = None

        async for step in graph.astream(initial_state):
            node_name = list(step.keys())[0]
            node_state = step[node_name]
            
            # Print node completion without raw_email
            print(f"\n✅ After node: [{node_name}]")
            
            # Print only relevant fields (exclude raw_email to avoid clutter)
            debug_state = {k: v for k, v in node_state.items() if k != 'raw_email'}
            print(f"  request_id: {debug_state.get('request_id', '')}")
            print(f"  status: {debug_state.get('status', '')}")
            print(f"  is_operator: {debug_state.get('is_operator', False)}")
            print(f"  shipment_found: {debug_state.get('shipment_found', False)}")
            
            final_state = node_state

        return final_state

    except Exception as e:
        print(f"❌ Workflow execution failed: {e}")
        return None
