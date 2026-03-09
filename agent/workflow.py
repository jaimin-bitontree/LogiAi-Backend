"""
agent/workflow.py

LangGraph workflow — agentic tool-calling architecture.

Pre-processing (fixed sequence, runs in order):
  parser → language → intent → reqid → context_builder

Agentic loop (LLM decides what tool to call next):
  agent ←→ tools  (loops until LLM has no more tool calls)
"""

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from agent.state import AgentState
from agent.nodes.parse_node import parser_node
from agent.nodes.language_node import language_node
from agent.nodes.intent_node import intent_node
from agent.nodes.reqid_generator_node import generate_reqid
from agent.nodes.context_builder_node import context_builder_node
from agent.agent_node import call_agent, TOOLS
from models.shipment import LanguageMetadata, ValidationResult, Attachment

# ── Build graph ───────────────────────────────────────────────
builder = StateGraph(AgentState)

# Pre-processing nodes (always run in fixed order)
builder.add_node("parser",          parser_node)
builder.add_node("language",        language_node)
builder.add_node("intent",          intent_node)
builder.add_node("reqid",           generate_reqid)
builder.add_node("context_builder", context_builder_node)  # Seeds agent with HumanMessage

# Agentic loop
builder.add_node("agent", call_agent)
builder.add_node("tools", ToolNode(TOOLS))

# ── Fixed pre-processing chain ────────────────────────────────
builder.add_edge(START,             "parser")
builder.add_edge("parser",          "language")
builder.add_edge("language",        "intent")
builder.add_edge("intent",          "reqid")
builder.add_edge("reqid",           "context_builder")
builder.add_edge("context_builder", "agent")           # Hand off to agent loop

# ── Agentic loop ──────────────────────────────────────────────
def should_continue(state: AgentState) -> str:
    """If LLM returned tool_calls → run tools. Otherwise → END.
    Also END if an email notification tool was just called."""
    messages = state["messages"]
    
    # Check if last tool call was an email notification
    if len(messages) >= 2:
        second_last = messages[-2]
        if hasattr(second_last, "tool_calls") and second_last.tool_calls:
            for tool_call in second_last.tool_calls:
                tool_name = tool_call.get("name", "")
                if "email" in tool_name.lower():
                    # Email was just sent, stop the loop
                    print("[workflow] Email tool was called, ending workflow")
                    return END
    
    # Normal check
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

builder.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
builder.add_edge("tools", "agent")  # Always loop back to agent after tool runs

graph = builder.compile()


# ── Initial state ─────────────────────────────────────────────

def create_initial_state(raw_email: bytes) -> AgentState:
    return {
        "raw_email":           raw_email,
        "request_id":          "",
        "thread_id":           None,
        "conversation_id":     None,
        "last_message_id":     None,
        "customer_email":      "",
        "subject":             None,
        "message_ids":         [],
        "body":                "",
        "translated_body":     "",
        "translated_subject":  "",
        "status":              "NEW",
        "intent":              None,
        "attachments":         [],
        "language_metadata":   LanguageMetadata(),
        "request_data":        {},
        "validation_result":   ValidationResult(),
        "pricing_details":     [],
        "messages":            [],   # Seeded properly by context_builder_node
        "final_document":      None,
    }


# ── Workflow runner ────────────────────────────────────────────

async def run_workflow(raw_email: bytes) -> AgentState:
    """
    Run the full pipeline:
      1. Pre-processing (parser, language, intent, reqid, context_builder)
      2. Agent loop (agent ↔ tools, LLM-driven)
    """
    try:
        initial_state = create_initial_state(raw_email)
        final_state   = None

        async for step in graph.astream(initial_state):
            node_name  = list(step.keys())[0]
            node_state = step[node_name]
            print(f"\n✅ After node: [{node_name}]")
            final_state = node_state

        if final_state:
            print(f"✅ Processed: {final_state.get('subject')}")
        else:
            print("⚠️  Workflow returned no final state")

        return final_state

    except Exception as e:
        print(f"❌ Workflow execution failed: {e}")
        raise
