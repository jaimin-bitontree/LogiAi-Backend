"""
agent/agent_node.py

The main LLM reasoning node for the agentic flow.
Binds the LLM to all available tools and defines how the agent
decides what action to take for each email.

Tools are SELF-CONTAINED — they handle DB saves internally.
The LLM only needs to decide WHICH tool to call, not manage DB.
"""

import logging
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, AIMessage

from config.settings import settings, GROQ_API_KEYS
from agent.tools.extraction_tool import extract_shipment_fields, extract_missing_field_values
from agent.tools.email_tools import send_missing_info_email, send_complete_info_emails
from agent.tools.pricing_tools import calculate_and_send_pricing
from agent.tools.status_tools import send_status_update, update_shipment_status
from agent.tools.confirmation_tools import process_shipment_confirmation
from agent.tools.cancellation_tools import cancel_shipment

logger = logging.getLogger(__name__)

# ── Only 4 tools — simple, small call signatures ─────────────
TOOLS = [
    extract_shipment_fields,
    extract_missing_field_values,
    send_missing_info_email,
    send_complete_info_emails,
    calculate_and_send_pricing,
    send_status_update,
    update_shipment_status,
    process_shipment_confirmation,
    cancel_shipment,
]

# ── Model fallback list (in order of preference) ──────────────
# Only 70B models support reliable tool calling
# 8B models generate malformed tool calls with LangChain
MODEL_FALLBACK = [
    "llama-3.3-70b-versatile",   # Only reliable option
]

def get_llm_with_tools():
    """
    Try to create LLM with tools, falling back through model list if rate limited.
    """
    for model_name in MODEL_FALLBACK:
        try:
            llm = ChatGroq(
                model=model_name,
                api_key=settings.GROQ_API_KEY,
                temperature=0.0,
            )
            llm_with_tools = llm.bind_tools(TOOLS, tool_choice="auto")
            logger.info(f"[agent_node] Using model: {model_name}")
            return llm_with_tools, model_name
        except Exception as e:
            logger.warning(f"[agent_node] Failed to initialize {model_name}: {e}")
            continue
    
    # If all fail, use the last one anyway (will error later but at least we tried)
    llm = ChatGroq(
        model=MODEL_FALLBACK[-1],
        api_key=settings.GROQ_API_KEY,
        temperature=0.0,
    )
    return llm.bind_tools(TOOLS, tool_choice="auto"), MODEL_FALLBACK[-1]

# ── System prompt (Clearer for 8B Model with Examples) ─────────────────
SYSTEM_PROMPT = """You are LogiAI, a logistics assistant that processes shipment requests.

You have access to these tools:
1. extract_shipment_fields(request_id: str) - Extract all fields from a new shipment request
2. extract_missing_field_values(request_id: str, missing_fields: list) - Extract specific missing fields from a reply
3. send_missing_info_email(request_id: str, customer_email: str, customer_name: str, subject: str, missing_fields: list) - Request missing information
4. send_complete_info_emails(request_id: str, customer_email: str, customer_name: str, subject: str) - Send confirmation when complete
5. calculate_and_send_pricing(request_id: str, pricing_email_body: str) - Process operator pricing and send quote
6. send_status_update(request_id: str, customer_email: str, last_message_id: str) - Send status update to customer
7. update_shipment_status(request_id: str, new_status: str) - Update shipment status in database
8. process_shipment_confirmation(request_id: str, customer_email: str) - Handle customer confirmation
9. cancel_shipment(request_id: str, customer_email: str) - Process cancellation request

WORKFLOW:

For intent "new_request":
1. Call extract_shipment_fields(request_id="REQ-...")
2. If extraction succeeds AND is_valid=false: Call send_missing_info_email with the missing_fields, then STOP IMMEDIATELY
3. If extraction succeeds AND is_valid=true: Call send_complete_info_emails, then STOP IMMEDIATELY
4. If extraction fails: STOP immediately

For intent "missing_information":
1. Call extract_missing_field_values(request_id="REQ-...", missing_fields=[...])
2. If extraction succeeds AND is_valid=false: Call send_missing_info_email with still_missing fields, then STOP IMMEDIATELY
3. If extraction succeeds AND is_valid=true: Call send_complete_info_emails, then STOP IMMEDIATELY
4. If extraction fails: STOP immediately

For intent "status_inquiry":
1. Call send_status_update(request_id="REQ-...", customer_email="...", last_message_id="..."), then STOP IMMEDIATELY

For intent "confirmation":
1. Call process_shipment_confirmation(request_id="REQ-...", customer_email="..."), then STOP IMMEDIATELY

For intent "cancellation":
1. Call cancel_shipment(request_id="REQ-...", customer_email="..."), then STOP IMMEDIATELY

For intent "operator_pricing":
1. Call calculate_and_send_pricing(request_id="REQ-...", pricing_email_body="..."), then STOP IMMEDIATELY

CRITICAL RULES:
- Extract request_id, customer_email, customer_name, subject from the input message
- Use the missing_fields list provided in the input
- ONLY send emails if extraction succeeds
- After calling ANY email tool, you MUST STOP - DO NOT CALL ANY MORE TOOLS
- NEVER call the same tool twice
- NEVER call multiple email tools in sequence
- Once you send an email, your job is COMPLETE - STOP IMMEDIATELY
- DO NOT CONTINUE THE CONVERSATION AFTER SENDING EMAILS
- EMAIL TOOLS ARE TERMINAL ACTIONS - THEY END THE WORKFLOW
"""

# Simpler prompt for 8B model (less reliable tool calling)
SYSTEM_PROMPT_8B = """You are a tool-calling agent. You MUST call tools, not write text.

Available tools:
1. extract_shipment_fields(request_id)
2. extract_missing_field_values(request_id, missing_fields)
3. send_missing_info_email(request_id, customer_email, customer_name, subject, missing_fields)
4. send_complete_info_emails(request_id, customer_email, customer_name, subject)

Rules:
- If intent="new_request": call extract_shipment_fields
- If intent="missing_information": call extract_missing_field_values
- After extraction, if is_valid=true: call send_complete_info_emails
- After extraction, if is_valid=false: call send_missing_info_email
- NEVER write explanations, ONLY call tools
- Stop after calling email tools

Extract all parameters from the input message.
"""


def call_agent(state: dict) -> dict:
    """
    The main agent reasoning node.
    Reads the current message history and calls the LLM with tools.
    The LLM decides which tool to call next (or ends the loop).
    Implements fallback strategy for rate limits and API key rotation.
    """
    
    # Try each API key
    last_error = None
    for api_key_index, api_key in enumerate(GROQ_API_KEYS):
        # Try each model with this API key
        for model_name in MODEL_FALLBACK:
            # Retry each model up to 2 times for transient errors
            for attempt in range(2):
                try:
                    # Use simpler prompt for 8B model
                    prompt = SYSTEM_PROMPT_8B if "8b" in model_name.lower() else SYSTEM_PROMPT
                    system_msg = SystemMessage(content=prompt)
                    messages = [system_msg] + state["messages"]
                    
                    llm = ChatGroq(
                        model=model_name,
                        api_key=api_key,
                        temperature=0.0,
                    )
                    
                    # For 8B model, try to force tool calling by being more explicit
                    if "8b" in model_name.lower():
                        llm_with_tools = llm.bind_tools(TOOLS)
                    else:
                        llm_with_tools = llm.bind_tools(TOOLS, tool_choice="auto")
                    
                    if attempt == 0:
                        key_label = f"Key {api_key_index + 1}/{len(GROQ_API_KEYS)}"
                        logger.info(f"[agent_node] Trying {model_name} with {key_label}")
                    else:
                        logger.info(f"[agent_node] Retrying {model_name} (attempt {attempt + 1})")
                        
                    response = llm_with_tools.invoke(messages)
                    
                    # Check if 8B model returned text instead of tool calls
                    if "8b" in model_name.lower() and not response.tool_calls and response.content:
                        logger.warning(f"[agent_node] 8B model returned text instead of tool call, skipping...")
                        logger.warning(f"[agent_node] 8B model failed to call tools")
                        break  # Don't retry, move to next model
                    
                    logger.info(f"[agent_node] Success with {model_name}")
                    logger.info(f"[agent_node] Tool calls: {response.tool_calls}")
                    
                    logger.info(
                        "[agent_node] LLM response | model=%s | api_key=%d | tool_calls=%d",
                        model_name,
                        api_key_index + 1,
                        len(response.tool_calls) if response.tool_calls else 0
                    )
                    
                    return {"messages": [response]}
                    
                except Exception as e:
                    error_str = str(e)
                    last_error = e
                    
                    # Check if it's a rate limit error - try next API key
                    if "rate_limit" in error_str.lower() or "429" in error_str:
                        logger.warning(f"[agent_node] Rate limit on key {api_key_index + 1}, trying next...")
                        logger.warning(f"[agent_node] Rate limit on API key {api_key_index + 1}")
                        break  # Break retry loop, try next model with this key
                    
                    # Check if it's a tool calling error - retry once
                    elif "tool_use_failed" in error_str or "invalid_request" in error_str:
                        if attempt == 0:
                            logger.warning(f"[agent_node] Tool error, retrying...")
                            logger.warning(f"[agent_node] Tool error, retrying...")
                            continue  # Retry same model
                        else:
                            logger.warning(f"[agent_node] Tool error persists, trying next model...")
                            logger.warning(f"[agent_node] Tool error persists, trying next...")
                            break  # Try next model
                    
                    # Other errors
                    else:
                        logger.error(f"[agent_node] Error: {e}")
                        logger.error(f"[agent_node] Error: {e}")
                        break
    
    # All API keys and models failed
    logger.error(f"[agent_node] All API keys and models failed. Last error: {last_error}")
    logger.error(f"[agent_node] All API keys exhausted. Last error: {last_error}")
    
    # Check if it was all rate limits
    if last_error and ("rate_limit" in str(last_error).lower() or "429" in str(last_error)):
        logger.warning(f"All {len(GROQ_API_KEYS)} API key(s) are rate limited!")
        logger.info("Solutions: 1. Wait 8-10 minutes for rate limits to reset")
        logger.info("2. Add more API keys to .env (GROQ_API_KEY_2, GROQ_API_KEY_3)")
        logger.info("3. Upgrade accounts to Groq Dev Tier")
        logger.info("4. Switch to OpenAI API")
    
    # Return error message to end workflow gracefully
    error_msg = AIMessage(content=f"All API keys failed. Last error: {str(last_error)}")
    return {"messages": [error_msg]}
