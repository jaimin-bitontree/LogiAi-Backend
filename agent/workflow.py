from langgraph.graph import StateGraph, START, END
from agent.state import AgentState
from agent.nodes.parse_node import parser_node
from agent.nodes.language_node import language_node
from agent.nodes.intent_node import intent_node
from models.shipment import LanguageMetadata, ValidationResult, Attachment
from agent.nodes.extraction_node import extraction_node
from agent.nodes.missing_info_node import missing_info_node
from agent.nodes.complete_info_node import complete_info_node
from agent.nodes.reqid_generator_node import generate_reqid
from agent.nodes.confirmation_node import confirmation_node

builder = StateGraph(AgentState)

builder.add_node("parser",       parser_node)
builder.add_node("language",     language_node)
builder.add_node("intent",       intent_node)
builder.add_node("reqid",        generate_reqid)
builder.add_node("extraction",   extraction_node)
builder.add_node("missing_info", missing_info_node)
builder.add_node("complete_info", complete_info_node)
builder.add_node("confirmation", confirmation_node)

builder.add_edge(START,      "parser")
builder.add_edge("parser",   "language")
builder.add_edge("language", "intent")


def route_after_intent(state: AgentState):
    intent = state.get("intent")
    if intent == "confirmation":
        return "confirmation"
    return "reqid"


builder.add_conditional_edges(
    "intent",
    route_after_intent,
    {
        "reqid":        "reqid",
        "confirmation": "confirmation",
    }
)

builder.add_edge("reqid", "extraction")


def route_after_extraction(state: AgentState):
    """Route based on whether all required fields were found."""
    val_res = state.get("validation_result")
    status = state.get("status")

    # If extraction node caught an exception (like the Pydantic schema mismatch)
    if status == "ERROR":
        print("⚠️ [workflow] Routing to END because extraction_node reported status='ERROR'")
        return END

    # If the email didn't trigger extraction, val_res remains default (is_valid=False, missing_fields=[])
    if not val_res:
        return END

    if val_res.is_valid:
        return "complete_info"
    elif val_res.missing_fields:
        return "missing_info"
    else:
        # no missing fields, but not valid -> extraction was skipped
        return END


builder.add_conditional_edges(
    "extraction",
    route_after_extraction,
    {
        "complete_info": "complete_info",
        "missing_info":  "missing_info",
        END: END
    }
)

builder.add_edge("missing_info",  END)
builder.add_edge("complete_info", END)
builder.add_edge("confirmation",  END)

graph = builder.compile()


def create_initial_state(raw_email: bytes) -> AgentState:
    return {
        "raw_email": raw_email,
        "request_id":       "",
        "thread_id":        None,
        "conversation_id":  None,
        "last_message_id":  None,
        "customer_email":   "",
        "subject":          None,
        "message_ids":      [],      
        "body":             "",
        "translated_body":  "",
        "translated_subject":  "",
        "status":           "NEW",
        "intent":           None,
        "attachments":      [],
        "language_metadata":  LanguageMetadata(),
        "request_data":       {},
        "validation_result":  ValidationResult(),
        "pricing_details":    [],
        "messages":           [],
        "final_document":     None,
    }


async def run_workflow(raw_email: bytes) -> AgentState:
    """
    Create initial state and invoke graph.
    Streams output so you can see state after each node.
    """
    try:
        initial_state = create_initial_state(raw_email)
        final_state = None

        async for step in graph.astream(initial_state):
            node_name = list(step.keys())[0]
            node_state = step[node_name]
            print(f"\n✅ After node: [{node_name}]")
            print(node_state)
            final_state = node_state

        return final_state

        if result:
            print(f"✅ Processed: {result.get('subject')}")
        else:
            print("⚠️ Workflow failed, result is None")
        return result
    except Exception as e:
        print(f"❌ Workflow execution failed: {e}")
