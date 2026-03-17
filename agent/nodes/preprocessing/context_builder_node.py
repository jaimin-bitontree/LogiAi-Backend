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
    conversation_id = state.get("conversation_id", "")
    request_data = state.get("request_data", {})
    validation = state.get("validation_result")
    
    if isinstance(validation, dict):
        missing_fields = validation.get("missing_fields", [])
    elif validation:
        missing_fields = getattr(validation, "missing_fields", [])
    else:
        missing_fields = []

    logger = logging.getLogger(__name__)
    
    logger.info(f"[context_builder_node] Seeding agent with intent={intent} | request_id={request_id}")
    
    # Handle spam emails early (reqid node was skipped)
    if intent == "spam":
        # For spam emails, request_id will be empty since reqid node was skipped
        # Set a placeholder
        request_id = "SPAM"
        
        seed_message = f"""
### SPAM EMAIL DETECTED ###
CUSTOMER_EMAIL: {customer_email}
SUBJECT: {subject}
ACTION: HANDLE SPAM

INSTRUCTIONS:
Call handle_spam_email() to send rejection template."""
        
        msg = HumanMessage(content=seed_message.strip())
        logger.debug(f"[context_builder_node] SPAM EMAIL SEED MESSAGE:\n{msg.content}\n")
        return {"messages": [msg]}
    
    # Extract customer_name from request_data if available
    customer_name = ""
    if isinstance(request_data, dict):
        required = request_data.get("required", {})
        if isinstance(required, dict):
            customer_name = required.get("customer_name", "")
    
    # Fallback to email if no customer_name found
    if not customer_name:
        customer_name = customer_email.split("@")[0] if customer_email else "Customer"

    # For operator_pricing intent, provide the FULL body since we need to extract pricing data
    # For other intents, provide only a snippet since tools fetch full data from DB
    if intent == "operator_pricing":
        body_snippet = body  # Full body needed for pricing extraction
    else:
        body_snippet = body[:200] + ("..." if len(body) > 200 else "")

    directive = "EXTRACT ALL FIELDS" if intent == "new_request" else f"EXTRACT MISSING FIELDS: {missing_fields}"
    
    # Build seed message with all parameters needed for tool calls
    seed_message = f"""
### INCOMING SHIPMENT EMAIL ###
REQUEST_ID: {request_id}
CUSTOMER_EMAIL: {customer_email}
CUSTOMER_NAME: {customer_name}
SUBJECT: {subject}
INTENT: {intent}
ACTION: {directive}
MISSING_FIELDS: {missing_fields}

EMAIL SNIPPET (INTERNAL DB RECORD):
---
{body_snippet}
---

INSTRUCTIONS: 
Use the appropriate extraction tool for the '{intent}' intent now.
When calling email tools, use these parameters:
- request_id: {request_id}
- customer_email: {customer_email}
- customer_name: {customer_name}
- subject: {subject}
- missing_fields: {missing_fields}"""
    
    msg = HumanMessage(content=seed_message.strip())
    logger.debug(f"[context_builder_node] SEED MESSAGE:\n{msg.content}\n")
    return {"messages": [msg]}
