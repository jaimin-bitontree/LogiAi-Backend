import asyncio
from email import policy
from email.parser import BytesParser
from groq import Groq
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
from services.ai.language_service import translate_text_to_language, detect_language
from langchain.tools import tool
import re
import logging
from models.shipment import Message
from services.shipment.shipment_service import (
    push_message_log,
    find_by_any_message_id,
    find_by_request_id
    )
from datetime import datetime
from services.email.email_sender import send_email
from services.email.email_template import build_email


logger = logging.getLogger(__name__)

# Groq client for attachment relevance check
_groq_client = Groq(api_key=settings.GROQ_API_KEY)


# ─────────────────────────────────────────────────────────────
# LLM RELEVANCE CHECK — private to parse_node
# ─────────────────────────────────────────────────────────────

def _check_attachment_relevance(page1_text: str, filename: str) -> bool:
    """
    Sends page 1 text of a PDF/Excel to LLM.
    Returns True if document contains shipment-related data, False if not.

    Only page 1 (first 1500 chars) is sent to keep token usage low.
    Safe fallback — if LLM fails, returns True to avoid losing data.
    """
    if not page1_text or not page1_text.strip():
        logger.warning(
            f"[parse_node] _check_attachment_relevance | "
            f"empty text for {filename} — marking irrelevant"
        )
        return False

    try:
        response = _groq_client.chat.completions.create(
            model=settings.LANGUAGE_DETECT_MODEL,
            temperature=0,
            max_tokens=10,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a logistics document classifier. "
                        "You will receive text from a document. "
                        "Your job is to decide if it contains shipment-related information. "
                        "\n\n"
                        "Shipment-related information includes ANY of these: "
                        "origin city, origin country, destination city, destination country, "
                        "cargo weight, volume, quantity, package type, container type, "
                        "shipment type, transport mode, incoterm, customer name, "
                        "contact person, description of goods, dangerous goods, stackable, "
                        "freight details, logistics data, packing list, bill of lading, "
                        "commercial invoice with shipping details. "
                        "\n\n"
                        "Reply with ONLY one word: YES or NO. "
                        "YES = document contains shipment-related data. "
                        "NO = document has no shipment-related data."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Does this document contain shipment-related information?\n\n"
                        f"{page1_text[:1500]}"
                    )
                }
            ]
        )

        answer      = response.choices[0].message.content.strip().upper()
        is_relevant = answer.startswith("YES")

        logger.info(
            f"[parse_node] Attachment relevance check | "
            f"filename={filename} | answer={answer} | is_relevant={is_relevant}"
        )
        return is_relevant

    except Exception as e:
        logger.error(
            f"[parse_node] Relevance check failed for {filename}: {e} "
            f"— defaulting to relevant (safe fallback)"
        )
        return True


# ─────────────────────────────────────────────────────────────
# ATTACHMENT PROCESSING
# ─────────────────────────────────────────────────────────────

async def _process_attachments(raw_attachments: list) -> tuple[list[Attachment], str]:
    """
    For each PDF/Excel attachment:
      1. Extract full text
      2. Send page 1 (first 1500 chars) to LLM for relevance check
      3. Relevant   → upload to Cloudinary, store url/public_id, is_relevant=True
                      append FULL text to body
      4. Irrelevant → dropped completely, not saved to DB, not uploaded

    All Cloudinary uploads happen in parallel using asyncio.gather().

    Returns:
        attachments:     List of RELEVANT Attachment objects only
        attachment_body: Combined text of all relevant attachments only
    """
    attachment_body = ""
    relevant_items  = []  # list of (att, raw_content, full_text, is_pdf)

    for raw_att in raw_attachments:
        filename     = (raw_att.get("filename") or "").lower()
        content_type = raw_att.get("content_type", "")
        raw_content  = raw_att.get("content")

        is_pdf = filename.endswith(".pdf") or content_type == "application/pdf"
        is_excel = (
            filename.endswith(".xlsx") or
            filename.endswith(".xls") or
            content_type in (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel",
            )
        )

        if not (is_pdf or is_excel):
            continue

        if not raw_content:
            logger.error(f"[parse_node] No content for attachment: {raw_att.get('filename')}")
            continue

        att = Attachment(
            filename=raw_att["filename"],
            content_type=raw_att["content_type"],
        )

        # Extract full text
        try:
            if is_pdf:
                full_text = extract_text_from_pdf(raw_content)
            else:
                full_text = extract_text_from_excel(raw_content)
        except Exception as e:
            logger.error(f"[parse_node] Text extraction failed: {att.filename} — {e}")
            full_text = ""

        if not full_text:
            logger.warning(f"[parse_node] No text extracted from {att.filename} — skipping")
            continue

        # LLM relevance check — page 1 only (first 1500 chars)
        is_relevant = _check_attachment_relevance(full_text[:1500], att.filename)

        if is_relevant:
            att.is_relevant = True
            relevant_items.append((att, raw_content, full_text, is_pdf))
            logger.info(f"[parse_node] Attachment relevant: {att.filename}")
        else:
            logger.info(
                f"[parse_node] Attachment irrelevant — not saving to DB or Cloudinary: {att.filename}"
            )

    # ── Upload ALL relevant attachments to Cloudinary in parallel ──
    if not relevant_items:
        return [], attachment_body

    logger.info(
        f"[parse_node] Uploading {len(relevant_items)} relevant attachment(s) "
        f"to Cloudinary in parallel"
    )

    async def _upload(att, raw_content, full_text, is_pdf):
        try:
            if is_pdf:
                result = await upload_pdf_to_cloudinary(raw_content, att.filename)
            else:
                result = await upload_excel_to_cloudinary(raw_content, att.filename)

            if result:
                att.public_id = result["public_id"]
                att.url       = result["url"]
                logger.info(
                    f"[parse_node] Uploaded to Cloudinary | "
                    f"filename={att.filename} | public_id={att.public_id}"
                )
            else:
                att.public_id = "upload_failed"
                att.url       = None
                logger.warning(f"[parse_node] Cloudinary upload failed: {att.filename}")
        except Exception as e:
            logger.error(f"[parse_node] Cloudinary upload exception: {att.filename} — {e}")
            att.public_id = "upload_error"
            att.url       = None
        return att, full_text

    # Run all uploads at the same time
    results = await asyncio.gather(*[
        _upload(att, raw_content, full_text, is_pdf)
        for att, raw_content, full_text, is_pdf in relevant_items
    ])

    # Build body from relevant attachments only
    relevant_attachments = []
    for att, full_text in results:
        relevant_attachments.append(att)
        filename_lower = (att.filename or "").lower()
        if filename_lower.endswith(".pdf") or att.content_type == "application/pdf":
            attachment_body += f"\n\n[PDF: {att.filename}]\n{full_text}"
        else:
            attachment_body += f"\n\n[EXCEL: {att.filename}]\n{full_text}"

    return relevant_attachments, attachment_body


# ─────────────────────────────────────────────────────────────
# PARSER NODE
# ─────────────────────────────────────────────────────────────

async def parser_node(state: AgentState) -> AgentState:

    raw_email = state["raw_email"]
    msg = BytesParser(policy=policy.default).parsebytes(raw_email)

    # Subject
    subject = msg.get("Subject", "")

    # Sender
    sender_raw     = msg.get("From", "")
    customer_email = extract_email_address(sender_raw)

    # IDs
    message_id        = (msg.get("Message-ID", "") or "").strip().strip("<>")
    in_reply_to       = msg.get("In-Reply-To", "")
    parent_message_id = in_reply_to.strip().strip("<>") if in_reply_to else None

    # Body
    raw_body   = extract_body(msg)
    clean_body = clean_email_body(raw_body)

    # Raw attachments from email
    raw_attachments = extract_attachments(msg)

    # Process attachments — LLM relevance check + parallel Cloudinary upload
    # Returns ONLY relevant attachments — irrelevant ones not saved anywhere
    attachments, attachment_body = await _process_attachments(raw_attachments)

    # Build final body — email body + relevant attachment content only
    updated_body = clean_body + attachment_body

    message_ids = state.get("message_ids")
    if not isinstance(message_ids, list):
        message_ids = []

    if message_id and message_id not in message_ids:
        message_ids.append(message_id)
        logger.debug(f"Message IDs: {message_ids}")

    # Check if operator
    is_operator = customer_email.lower() == settings.OPERATOR_EMAIL.lower()

    # Lookup shipment if operator email (multi-strategy)
    request_id     = ""
    shipment_found = False

    if is_operator:
        logger.info(f"[parse_node] Operator email detected")
        logger.info(f"[parse_node] Subject: {subject}")
        logger.info(f"[parse_node] In-Reply-To: {parent_message_id}")

        # Strategy 1: Lookup by In-Reply-To header
        if parent_message_id:
            shipment = await find_by_any_message_id(parent_message_id)

            if shipment:
                logger.info(f"[parse_node] ✅ Found shipment by In-Reply-To: {parent_message_id}")
                logger.info(f"[parse_node] ✅ Matched request_id: {shipment.request_id}")
                shipment_found = True
                request_id     = shipment.request_id

                operator_message = Message(
                    message_id=message_id,
                    sender_email=customer_email,
                    sender_type="operator",
                    direction="incoming",
                    subject=subject,
                    body=updated_body,
                    attachments=attachments,
                    received_at=datetime.utcnow()
                )

                await push_message_log(
                    request_id=shipment.request_id,
                    message=operator_message.model_dump(),
                    sent_message_id=message_id,
                    status=shipment.status,
                )

                logger.info(
                    f"[parse_node] Operator email logged | "
                    f"request_id={shipment.request_id} | msg_id={message_id}"
                )

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
                        "translated_body": translate_text_to_language(updated_body, "en") if detect_language(updated_body[:500])[0] != "en" else updated_body,
                        "attachments": attachments,
                    })
                return state

        # Strategy 2: Extract request_id from subject line
        if not shipment_found:
            logger.info(f"[parse_node] No In-Reply-To match, trying request_id extraction from subject...")
            match = re.search(r'REQ-\d{4}-\d+', subject)

            if match:
                request_id = match.group(0)
                logger.info(f"[parse_node] ✅ Extracted request_id from subject: {request_id}")
                
                shipment = await find_by_request_id(request_id)

                if shipment:
                    logger.info(f"[parse_node] ✅ Found shipment by request_id: {request_id}")
                    shipment_found = True

                    state.update({
                        "message_ids":        message_ids,
                        "last_message_id":    message_id,
                        "request_id":         shipment.request_id,
                        "customer_email":     shipment.customer_email,
                        "request_data":       shipment.request_data,
                        "status":             shipment.status,
                        "pricing_details":    shipment.pricing_details,
                        "is_operator":        is_operator,
                        "shipment_found":     shipment_found,
                        "subject":            subject,
                        "body":               updated_body,
                        "translated_subject": subject,
                        "translated_body": translate_text_to_language(updated_body, "en") if detect_language(updated_body[:500])[0] != "en" else updated_body,
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
                
                shipment = await find_by_request_id(request_id)

                if shipment:
                    logger.info(f"[parse_node] ✅ Found shipment by request_id: {request_id}")
                    shipment_found = True

                    state.update({
                        "message_ids":        message_ids,
                        "last_message_id":    message_id,
                        "request_id":         shipment.request_id,
                        "customer_email":     shipment.customer_email,
                        "request_data":       shipment.request_data,
                        "status":             shipment.status,
                        "pricing_details":    shipment.pricing_details,
                        "is_operator":        is_operator,
                        "shipment_found":     shipment_found,
                        "subject":            subject,
                        "body":               updated_body,
                        "translated_subject": subject,
                        "translated_body": translate_text_to_language(updated_body, "en") if detect_language(updated_body[:500])[0] != "en" else updated_body,
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

            request_id_missing  = not request_id or request_id == ""
            in_reply_to_missing = not parent_message_id or parent_message_id == ""

            if request_id_missing and in_reply_to_missing:
                # Send guidance email to operator
                
                operator_guidance_html = build_email(
                    email_type="missing_info",
                    customer_name="Operator",
                    request_id="UNKNOWN",
                    missing_fields=["request_id"],
                    message=(
                        "We received your pricing email but couldn't match it to any shipment. "
                        "Please reply to this email with the Request ID (format: REQ-YYYY-XXXXXXXXXXXX) "
                        "or reply directly to the customer's original email."
                    )
                )

                msg_id = send_email(
                    to=customer_email,  # Send to the operator who sent the email
                    subject="Request ID Required - Cannot Process Pricing",
                    body_html=operator_guidance_html,
                    request_id="UNKNOWN"
                )

                logger.info(f"[parse_node] Guidance email sent to operator | msg_id={msg_id}")
                logger.info(f"[parse_node] Stopping workflow - operator email cannot be matched")
                
                # Set flag to stop workflow and update minimal state
                state["operator_guidance_sent"] = True
                state["is_operator"] = True  
                state["customer_email"] = customer_email
                state["subject"] = subject
                state["body"] = updated_body
                
                return state

    # Update state — only relevant attachments saved
    state.update({
        "message_ids":     message_ids,
        "last_message_id": message_id,
        "thread_id":       message_id,
        "conversation_id": parent_message_id,
        "customer_email":  customer_email if not shipment_found else state.get("customer_email"),
        "is_operator":     is_operator,
        "shipment_found":  shipment_found,
        "subject":         subject,
        "body":            updated_body,
        "attachments":     attachments,
    })

    return state