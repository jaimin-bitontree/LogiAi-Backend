"""
agent/workflow.py

LangGraph workflow — agentic tool-calling architecture.

Pre-processing (fixed sequence, runs in order):
  parser → language → intent → reqid → context_builder

Agentic loop (LLM decides what tool to call next):
  agent ←→ tools  (loops until LLM has no more tool calls)
"""

import logging
from langgraph.graph import StateGraph, START, END
# from langgraph.prebuilt import ToolNode  # Not available in this version

from agent.state import AgentState
from agent.nodes.preprocessing.parse_node import parser_node
from agent.nodes.preprocessing.language_node import language_node
from agent.nodes.preprocessing.intent_node import intent_node
from agent.nodes.preprocessing.reqid_generator_node import generate_reqid
from agent.nodes.preprocessing.context_builder_node import context_builder_node
from agent.agent_node import call_agent, TOOLS
from models.shipment import LanguageMetadata, ValidationResult, Attachment

logger = logging.getLogger(__name__)


# Custom ToolNode implementation since prebuilt is not available
class ToolNode:
    def __init__(self, tools):
        self.tools = {tool.name: tool for tool in tools}
    
    async def __call__(self, state):
        messages = state["messages"]
        last_message = messages[-1]
        
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return {"messages": []}
        
        tool_messages = []
        email_tool_executed = False
        
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            # Check if this is an email-sending tool
            email_sending_tools = [
                "send_missing_info_email",
                "send_complete_info_emails", 
                "send_status_update",
                "calculate_and_send_pricing",
                "process_shipment_confirmation",
                "cancel_shipment"
            ]
            
            if tool_name in email_sending_tools:
                email_tool_executed = True
            
            if tool_name in self.tools:
                try:
                    tool = self.tools[tool_name]
                    result = await tool.ainvoke(tool_args)
                    
                    from langchain_core.messages import ToolMessage
                    tool_message = ToolMessage(
                        content=str(result),
                        tool_call_id=tool_id
                    )
                    tool_messages.append(tool_message)
                    
                    # Log email tool execution
                    if email_tool_executed:
                        logger.info(f"[ToolNode] Email tool '{tool_name}' executed successfully")
                        
                except Exception as e:
                    from langchain_core.messages import ToolMessage
                    error_message = ToolMessage(
                        content=f"Error: {str(e)}",
                        tool_call_id=tool_id
                    )
                    tool_messages.append(error_message)
        
        # Add a flag to state if email tool was executed
        result = {"messages": tool_messages}
        if email_tool_executed:
            result["email_tool_executed"] = True
            
        return result

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
    """If LLM returned tool_calls → run tools. Otherwise → END."""
    messages = state["messages"]
    
    if not messages:
        return END
    
    last_message = messages[-1]
    
    # If agent wants to call more tools, continue
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
        "shipment_found":      False,
        "is_operator":         False,
        "email_tool_executed": False,
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
            logger.info(f"After node: [{node_name}]")
            final_state = node_state

        if final_state:
            logger.info(f"Processed: {final_state.get('subject')}")
        else:
            logger.warning("Workflow returned no final state")

        return final_state

    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        raise
