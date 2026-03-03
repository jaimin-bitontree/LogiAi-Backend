from langgraph.graph import StateGraph, START, END
from agent.state import AgentState
from agent.nodes.parse_node import parser_node


builder = StateGraph(AgentState)

builder.add_node("parser", parser_node)

builder.add_edge(START, "parser")
builder.add_edge("parser", END)

graph = builder.compile()


def create_initial_state(raw_email: bytes) -> AgentState:
    return {
        "raw_email": raw_email,
        "request_id": "",
        "thread_id": None,
        "customer_email": "",
        "subject": "",
        "message_ids": "",
        "status": "",
        "intent": "",
        "attachments": {},
    }


def run_workflow(raw_email: bytes) -> AgentState:
    """
    Create initial state and invoke graph.
    """
    try:

        initial_state = create_initial_state(raw_email)
        result = graph.invoke(initial_state)

        print(result)
        return result
    except Exception as e:
        print(f"❌ Workflow execution failed: {e}")
