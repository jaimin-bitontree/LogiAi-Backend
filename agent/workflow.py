from langgraph.graph import StateGraph, START, END
from agent.state import AgentState
from agent.nodes.parse_node import parser_node
from agent.nodes.language_node import language_node
from agent.nodes.intent_node import intent_node
from models.shipment import LanguageMetadata, ValidationResult, Attachment
from agent.nodes.reqid_generator_node import generate_reqid

builder = StateGraph(AgentState)

builder.add_node("parser",   parser_node)
builder.add_node("language", language_node)
builder.add_node("intent",   intent_node)
builder.add_node("reqid", generate_reqid)

builder.add_edge(START,      "parser")
builder.add_edge("parser",   "language")
builder.add_edge("language","intent")
builder.add_edge("intent","reqid")
builder.add_edge("reqid", END)

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
