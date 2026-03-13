from email import policy
from email.parser import BytesParser
from models.shipment import Attachment
from utils.email.email_utils import (
    extract_email_address,
    extract_body,
    clean_email_body,
    extract_attachments,
)
from utils.email.attachment_helper import extract_text_from_pdf, extract_text_from_excel
from utils.cloudinary_service import upload_pdf_to_cloudinary, upload_excel_to_cloudinary
from agent.state import AgentState
from config.settings import settings
from langchain.tools import tool
import re
import logging

logger = logging.getLogger(__name__)


# tool — append PDF text to body

@tool
def append_pdf_text_to_body(body: str, pdf_filename: str, pdf_text: str) -> str:
    """
    Appends extracted PDF text to the email body.
    Called once per PDF attachment found in the email.
    Returns the combined body string.
    """
    if pdf_text:
        return body + f"\n\n[PDF: {pdf_filename}]\n{pdf_text}"
    return body


# tool — append Excel text to body

@tool
def append_excel_text_to_body(body: str, excel_filename: str, excel_text: str) -> str:
    """
    Appends extracted Excel text to the email body.
    Called once per Excel attachment found in the email.
    Returns the combined body string.
    """
    if excel_text:
        return body + f"\n\n[EXCEL: {excel_filename}]\n{excel_text}"
    return body


# langgraph node





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
            content_type=a["content_type"],
           
        )
        for a in raw_attachments
    ]

    # PDF + Excel extraction — append to body via @tool
    updated_body = clean_body
    for att in attachments:
        filename = (att.filename or "").lower()

        is_pdf = filename.endswith(".pdf") or att.content_type == "application/pdf"
        is_excel = (
            filename.endswith(".xlsx") or
            filename.endswith(".xls") or
            att.content_type in (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel",
            )
        )

        if is_pdf:
            try:
                logger.info(f"[parse_node] Extracting PDF: {att.filename}")
                pdf_text = extract_text_from_pdf(att.content)
                if not pdf_text:
                    logger.warning(f"[parse_node] No text extracted from {att.filename} — may be scanned or image-based PDF")
                    updated_body += f"\n\n[WARNING: Could not read {att.filename} — please resend as a digital PDF]"
                else:
                    updated_body = append_pdf_text_to_body.invoke({
                        "body": updated_body,
                        "pdf_filename": att.filename,
                        "pdf_text": pdf_text,
                    })
                    logger.info(f"[parse_node] Extracted {len(pdf_text)} chars from {att.filename}")
                
                # Upload PDF to Cloudinary
                logger.info(f"[parse_node] Uploading PDF to Cloudinary: {att.filename}")
                cloudinary_result = await upload_pdf_to_cloudinary(att.content, att.filename)
                if cloudinary_result:
                    att.public_id = cloudinary_result["public_id"]
                    att.url = cloudinary_result["url"]
                    logger.info(f"[parse_node] PDF uploaded to Cloudinary | public_id={att.public_id}")
                else:
                    logger.warning(f"[parse_node] Failed to upload PDF to Cloudinary: {att.filename}")
                    
            except Exception as e:
                logger.error(f"[parse_node] PDF extraction failed: {att.filename} — {e}")
                updated_body += f"\n\n[WARNING: Could not read {att.filename} — please resend as a digital PDF]"

        elif is_excel:
            try:
                logger.info(f"[parse_node] Extracting Excel: {att.filename}")
                excel_text = extract_text_from_excel(att.content)
                if not excel_text:
                    logger.warning(f"[parse_node] No text extracted from {att.filename} — file may be empty")
                    updated_body += f"\n\n[WARNING: Could not read {att.filename} — please resend as a valid Excel file]"
                else:
                    updated_body = append_excel_text_to_body.invoke({
                        "body": updated_body,
                        "excel_filename": att.filename,
                        "excel_text": excel_text,
                    })
                    logger.info(f"[parse_node] Extracted {len(excel_text)} chars from {att.filename}")
                
                # Upload Excel to Cloudinary
                logger.info(f"[parse_node] Uploading Excel to Cloudinary: {att.filename}")
                cloudinary_result = await upload_excel_to_cloudinary(att.content, att.filename)
                if cloudinary_result:
                    att.public_id = cloudinary_result["public_id"]
                    att.url = cloudinary_result["url"]
                    
                    logger.info(f"[parse_node] Excel uploaded to Cloudinary | public_id={att.public_id}")
                else:
                    logger.warning(f"[parse_node] Failed to upload Excel to Cloudinary: {att.filename}")
                    
            except Exception as e:
                logger.error(f"[parse_node] Excel extraction failed: {att.filename} — {e}")
                updated_body += f"\n\n[WARNING: Could not read {att.filename} — please resend as a valid Excel file]"

    message_ids = state.get("message_ids")
    if not isinstance(message_ids, list):
        message_ids = []

    if message_id and message_id not in message_ids:
        message_ids.append(message_id)
        logger.debug(f"Message IDs: {message_ids}")

    # Check if operator
    is_operator = customer_email.lower() == settings.OPERATOR_EMAIL.lower()
    
    # Lookup shipment if operator email (multi-strategy)
    request_id = ""
    shipment_found = False
    
    if is_operator:
        logger.info(f"[parse_node] Operator email detected")
        logger.info(f"[parse_node] Subject: {subject}")
        logger.info(f"[parse_node] In-Reply-To: {parent_message_id}")
        
        # Strategy 1: Lookup by In-Reply-To header (reply email - most reliable)
        if parent_message_id:
            from services.shipment.shipment_service import find_by_any_message_id
            shipment = await find_by_any_message_id(parent_message_id)
            
            if shipment:
                logger.info(f"[parse_node] ✅ Found shipment by In-Reply-To: {parent_message_id}")
                logger.info(f"[parse_node] ✅ Matched request_id: {shipment.request_id}")
                shipment_found = True
                request_id = shipment.request_id
                
               
        
                # Update state and return early
                state.update({
                        "message_ids": message_ids,
                        "last_message_id": message_id,
                        "request_id":shipment.request_id,
                        "customer_email":shipment.customer_email,
                        "request_data":shipment.request_data,
                        "status":shipment.status,
                        "pricing_details":shipment.pricing_details,
                        "is_operator": is_operator,
                        "shipment_found": shipment_found,
                        "subject": subject,
                        "body": updated_body,
                        "translated_subject": subject,      
                        "translated_body": updated_body,   
                        "attachments": attachments,
                    })
                return state
        
        # Strategy 2: Extract request_id from subject line (separate email)
        if not shipment_found:
            logger.info(f"[parse_node] No In-Reply-To match, trying request_id extraction from subject...")
            match = re.search(r'REQ-\d{4}-\d+', subject)
            
            if match:
                request_id = match.group(0)
                logger.info(f"[parse_node] ✅ Extracted request_id from subject: {request_id}")
                
                from services.shipment.shipment_service import find_by_request_id
                shipment = await find_by_request_id(request_id)
                
                if shipment:
                    logger.info(f"[parse_node] ✅ Found shipment by request_id: {request_id}")
                    shipment_found = True
                    
                    
                    # Update state and return early
                    state.update({
                        "message_ids": message_ids,
                        "last_message_id": message_id,
                        "request_id":shipment.request_id,
                        "customer_email":shipment.customer_email,
                        "request_data":shipment.request_data,
                        "status":shipment.status,
                        "pricing_details":shipment.pricing_details,
                        "is_operator": is_operator,
                        "shipment_found": shipment_found,
                        "subject": subject,
                        "body": updated_body,
                        "translated_subject": subject,      
                        "translated_body": updated_body,   
                        "attachments": attachments,
                    })
                    return state
                else:
                    logger.warning(f"[parse_node] ❌ No shipment found for request_id: {request_id}")
        
        # Strategy 3: Extract request_id from body (fallback)
        if not shipment_found:
            logger.info(f"[parse_node] No match in subject, trying request_id extraction from body...")
            match = re.search(r'REQ-\d{4}-\d+', clean_body)
            
            if match:
                request_id = match.group(0)
                logger.info(f"[parse_node] ✅ Extracted request_id from body: {request_id}")
                
                from services.shipment.shipment_service import find_by_request_id
                shipment = await find_by_request_id(request_id)
                
                if shipment:
                    logger.info(f"[parse_node] ✅ Found shipment by request_id: {request_id}")
                    shipment_found = True
                    
                    
                    # Update state and return early
                    state.update({
                        "message_ids": message_ids,
                        "last_message_id": message_id,
                        "request_id":shipment.request_id,
                        "customer_email":shipment.customer_email,
                        "request_data":shipment.request_data,
                        "status":shipment.status,
                        "pricing_details":shipment.pricing_details,
                        "is_operator": is_operator,
                        "shipment_found": shipment_found,
                        "subject": subject,
                        "body": updated_body,
                        "translated_subject": subject,      
                        "translated_body": updated_body,   
                        "attachments": attachments,
                    })
                    return state
                else:
                    logger.warning(f"[parse_node] ❌ No shipment found for request_id: {request_id}")
            else:
                logger.warning(f"[parse_node] ❌ No request_id pattern found in body")
        
        # Final check
        if not shipment_found:
            logger.error(f"[parse_node] ❌ Cannot match operator email to any shipment")
            logger.error(f"[parse_node] Tried: In-Reply-To, subject line, body text")

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
        "body": updated_body,
        "attachments": attachments,
    })

    return state
