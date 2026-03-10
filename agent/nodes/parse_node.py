from email import policy
from email.parser import BytesParser
from models.shipment import Attachment
from utils.email_utils import (
    extract_email_address,
    extract_body,
    clean_email_body,
    extract_attachments,
)
from models.shipment import Attachment
from agent.state import AgentState
from config import settings
import re


async def parser_node(state: AgentState) -> AgentState:

    raw_email = state["raw_email"]
    msg = BytesParser(policy=policy.default).parsebytes(raw_email)

    # Subject
    subject = msg.get("Subject", "")

    # Sender
    sender_raw = msg.get("From", "")
    customer_email = extract_email_address(sender_raw)

    # IDs
    message_id = (msg.get("Message-ID", "") or "").strip().strip("<>")
    in_reply_to = msg.get("In-Reply-To", "")
    parent_message_id = in_reply_to.strip().strip("<>") if in_reply_to else None

    # Body
    raw_body = extract_body(msg)
    clean_body = clean_email_body(raw_body)

    # Attachments — convert raw dicts to Attachment objects
    raw_attachments = extract_attachments(msg)
    attachments = [
        Attachment(
            filename=a["filename"],
            content_type=a["content_type"]
        )
        for a in raw_attachments
    ]

    message_ids = state.get("message_ids")
    if not isinstance(message_ids, list):
        message_ids = []
    
    if message_id and message_id not in message_ids:
        message_ids.append(message_id)
        print(message_ids)

    # Check if operator
    is_operator = customer_email.lower() == settings.OPERATOR_EMAIL.lower()
    
    # Lookup shipment if operator email (multi-strategy)
    request_id = ""
    shipment_found = False
    
    if is_operator:
        print(f"[parse_node] Operator email detected")
        print(f"[parse_node] Subject: {subject}")
        print(f"[parse_node] In-Reply-To: {parent_message_id}")
        
        # Strategy 1: Lookup by In-Reply-To header (reply email - most reliable)
        if parent_message_id:
            from services.shipment_service import find_by_any_message_id
            shipment = await find_by_any_message_id(parent_message_id)
            
            if shipment:
                print(f"[parse_node] ✅ Found shipment by In-Reply-To: {parent_message_id}")
                print(f"[parse_node] ✅ Matched request_id: {shipment.request_id}")
                shipment_found = True
                request_id = shipment.request_id
                
                # Hydrate state with shipment data
                state["request_id"] = shipment.request_id
                state["customer_email"] = shipment.customer_email  # Override with actual customer
                state["request_data"] = shipment.request_data
                state["status"] = shipment.status
                state["pricing_details"] = shipment.pricing_details
                state["messages"] = shipment.messages
        
        # Strategy 2: Extract request_id from subject line (separate email)
        if not shipment_found:
            print(f"[parse_node] No In-Reply-To match, trying request_id extraction from subject...")
            match = re.search(r'REQ-\d{4}-\d+', subject)
            
            if match:
                request_id = match.group(0)
                print(f"[parse_node] ✅ Extracted request_id from subject: {request_id}")
                
                from services.shipment_service import find_by_request_id
                shipment = await find_by_request_id(request_id)
                
                if shipment:
                    print(f"[parse_node] ✅ Found shipment by request_id: {request_id}")
                    shipment_found = True
                    
                    # Hydrate state with shipment data
                    state["request_id"] = shipment.request_id
                    state["customer_email"] = shipment.customer_email
                    state["request_data"] = shipment.request_data
                    state["status"] = shipment.status
                    state["pricing_details"] = shipment.pricing_details
                    state["messages"] = shipment.messages
                else:
                    print(f"[parse_node] ❌ No shipment found for request_id: {request_id}")
        
        # Strategy 3: Extract request_id from body (fallback)
        if not shipment_found:
            print(f"[parse_node] No match in subject, trying request_id extraction from body...")
            match = re.search(r'REQ-\d{4}-\d+', clean_body)
            
            if match:
                request_id = match.group(0)
                print(f"[parse_node] ✅ Extracted request_id from body: {request_id}")
                
                from services.shipment_service import find_by_request_id
                shipment = await find_by_request_id(request_id)
                
                if shipment:
                    print(f"[parse_node] ✅ Found shipment by request_id: {request_id}")
                    shipment_found = True
                    
                    # Hydrate state with shipment data
                    state["request_id"] = shipment.request_id
                    state["customer_email"] = shipment.customer_email
                    state["request_data"] = shipment.request_data
                    state["status"] = shipment.status
                    state["pricing_details"] = shipment.pricing_details
                    state["messages"] = shipment.messages
                else:
                    print(f"[parse_node] ❌ No shipment found for request_id: {request_id}")
            else:
                print(f"[parse_node] ❌ No request_id pattern found in body")
        
        # Final check
        if not shipment_found:
            print(f"[parse_node] ❌ Cannot match operator email to any shipment")
            print(f"[parse_node] Tried: In-Reply-To, subject line, body text")

    # Update state
    state.update({
        "message_ids": message_ids,
        "last_message_id": message_id,
        "thread_id": message_id,
        "conversation_id": parent_message_id,
        "customer_email": customer_email if not shipment_found else state.get("customer_email"),
        "is_operator": is_operator,
        "shipment_found": shipment_found,  # Flag for routing
        "subject": subject,
        "body": clean_body,
        "attachments": attachments,
    })

    return state
