"""
agent/nodes/context_builder_node.py

Runs after all pre-processing nodes (parser, language, intent, reqid).
Builds the initial HumanMessage that seeds the LLM agent loop with
all the context it needs to start reasoning about the email.

This is the correct LangGraph way to inject the first agent message:
by returning {"messages": [HumanMessage(...)]} from a graph node.
"""

from langchain_core.messages import HumanMessage
from agent.state import AgentState
import logging



def context_builder_node(state: AgentState) -> dict:
    """
    Builds the first HumanMessage for the agent based on all the
    data that was collected during pre-processing (parse, language, intent, reqid).
    Returns it as {"messages": [HumanMessage(...)]} so the add_messages
    reducer appends it to the state correctly.
    """
    intent = state.get("intent", "unknown")
    customer_email = state.get("customer_email", "")
    subject = state.get("subject", "")
    body = state.get("translated_body", "")
    request_id = state.get("request_id", "")
    request_data = state.get("request_data", {})
    validation = state.get("validation_result")
    
    if isinstance(validation, dict):
        missing_fields = validation.get("missing_fields", [])
    elif validation:
        missing_fields = getattr(validation, "missing_fields", [])
    else:
        missing_fields = []

    # For operator_pricing intent, provide the FULL body since we need to extract pricing data
    # For other intents, provide only a snippet since tools fetch full data from DB
    if intent == "operator_pricing":
        body_snippet = body  # Full body needed for pricing extraction
    else:
        body_snippet = body[:200] + ("..." if len(body) > 200 else "")

    logger = logging.getLogger(__name__)
    
    logger.info(f"[context_builder_node] Seeding agent with intent={intent} | request_id={request_id}")
    
    directive = "EXTRACT ALL FIELDS" if intent == "new_request" else f"EXTRACT MISSING FIELDS: {missing_fields}"
    
    seed_message = f"""
### INCOMING SHIPMENT EMAIL ###
REQUEST_ID: {request_id}
CUSTOMER  : {customer_email}
INTENT    : {intent}
ACTION    : {directive}

EMAIL SNIPPET (INTERNAL DB RECORD):
---
{body_snippet}
---

INSTRUCTIONS: 
Use the appropriate extraction tool for the '{intent}' intent now."""
    
    msg = HumanMessage(content=seed_message.strip())
    logger.debug(f"[context_builder_node] SEED MESSAGE:\n{msg.content}\n")
    return {"messages": [msg]}
