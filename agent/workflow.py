from langgraph.graph import StateGraph, START, END
from agent.state import AgentState
from agent.nodes.parse_node import parser_node
from agent.nodes.language_node import language_node
from agent.nodes.intent_node import intent_node
from agent.nodes.extraction_node import extraction_node
from agent.nodes.missing_info_node import missing_info_node
from agent.nodes.complete_info_node import complete_info_node
from agent.nodes.reqid_generator_node import generate_reqid
from agent.nodes.status_node import status_handler
from agent.nodes.cancellation_node import cancellation_handler
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
builder.add_node("status",        status_handler)
builder.add_node("cancellation",  cancellation_handler)

# ── Routers ────────────────────────────────────────────────────
def intent_router(state: AgentState):
    """Decide next node based on detected intent."""
    intent = state.get("intent")
    
    if intent == EmailIntent.STATUS_INQUIRY:
        return "status"
    
    if intent == EmailIntent.CANCELLATION:
        return "cancellation"
    
    if intent in [EmailIntent.NEW_REQUEST, EmailIntent.MISSING_INFORMATION]:
        return "reqid"
    
    return END

def extraction_router(state: AgentState):
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
builder.add_edge(START,      "parser")
builder.add_edge("parser",   "language")
builder.add_edge("language", "intent")

builder.add_conditional_edges(
    "intent",
    intent_router,
    {
        "status": "status",
        "cancellation": "cancellation",
        "reqid":  "reqid",
        END: END
    }
)

builder.add_edge("reqid",      "extraction")

builder.add_conditional_edges(
    "extraction", 
    extraction_router,
    {
        "complete_info": "complete_info",
        "missing_info":  "missing_info",
        END: END
    }
)

# Terminal Edges
builder.add_edge("status",        END)
builder.add_edge("cancellation",  END)
builder.add_edge("missing_info",  END) # Stop after requesting more info
builder.add_edge("complete_info", END) # Stop after notifying operator

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
        "final_document":     None,
    }


async def run_workflow(raw_email: bytes) -> AgentState:
    """
    Create initial state and invoke graph using astream (async).
    """
    try:
        initial_state = create_initial_state(raw_email)
        final_state = initial_state # Fallback

        async for step in graph.astream(initial_state):
            node_name = list(step.keys())[0]
            node_state = step[node_name]
            print(f"\n✅ After node: [{node_name}]")
            final_state = node_state

        return final_state

    except Exception as e:
        print(f"❌ Workflow execution failed: {e}")
        return None
