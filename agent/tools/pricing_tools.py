"""
agent/tools/pricing_tools.py

Agentic tools for pricing operations.
Converted from agent/nodes/pricing_node.py
"""

import logging
from datetime import datetime
from langchain_core.tools import tool

from config.settings import settings
from config.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import Message, PricingSchema
from services.ai.pricing_service import extract_pricing_data
from services.ai.language_service import translate_to_language, translate_text_to_language
from services.email.email_sender import send_email
from services.email.email_template import build_email
from services.shipment.shipment_service import push_message_log, get_shipment_by_request_id, set_pricing_details

logger = logging.getLogger(__name__)


def merge_pricing_data(existing_pricing: PricingSchema, new_pricing: PricingSchema) -> PricingSchema:
    """Merge new pricing with existing pricing intelligently.
    
    New values override existing, but missing fields in new data keep existing values.
    
    Args:
        existing_pricing: Existing PricingSchema object
        new_pricing: New PricingSchema object from operator email
        
    Returns:
        Merged PricingSchema object
    """
    logger.debug(f"[merge_pricing_data] Merging pricing data")
    
    existing_dict = existing_pricing.model_dump()
    new_dict = new_pricing.model_dump()
    
    merged_dict = {}
    
    for field, new_value in new_dict.items():
        if new_value is not None and new_value != "" and new_value != []:
            merged_dict[field] = new_value
            logger.debug(f"  {field}: using new value")
        else:
            merged_dict[field] = existing_dict.get(field)
            logger.debug(f"  {field}: keeping existing value")
    
    logger.debug(f"[merge_pricing_data] Merge complete")
    return PricingSchema(**merged_dict)


@tool
async def calculate_and_send_pricing(request_id: str, pricing_email_body: str) -> str:
    """Calculate pricing from operator email and send quote to customer.
    
    Args:
        request_id: The shipment request ID
        pricing_email_body: Email body containing pricing information from operator
        
    Returns:
        Confirmation string with sent message ID
    """
    try:
        logger.info(f"[pricing_tools] Processing pricing for {request_id}")
        logger.debug(f"Starting pricing extraction for {request_id}")
        logger.debug(f"Email body length: {len(pricing_email_body)} chars")
        logger.debug(f"Email body preview: {pricing_email_body[:200]}...")

        # 1. Extract pricing data from email body
        logger.debug(f"Calling extract_pricing_data...")
        pricing_data, extracted_request_id = extract_pricing_data(pricing_email_body)
        logger.debug(f"Extraction result - pricing_data: {pricing_data is not None}")
        logger.debug(f"Extraction result - extracted_request_id: {extracted_request_id}")
        
        if not pricing_data:
            error_msg = "Failed to extract pricing data from email"
            logger.error(f"{error_msg}")
            return {"success": False, "error": error_msg}

        logger.debug(f"Pricing data extracted successfully: {pricing_data.model_dump()}")

        # 2. Get shipment data from DB
        logger.debug(f"Getting shipment from DB...")
        shipment_doc = await get_shipment_by_request_id(request_id)
        if not shipment_doc:
            error_msg = f"Shipment {request_id} not found"
            logger.error(f"{error_msg}")
            return {"success": False, "error": error_msg}

        logger.debug(f"Shipment found: {shipment_doc.get('customer_email')}")

        customer_email = shipment_doc["customer_email"]
        request_data   = shipment_doc.get("request_data", {})
        customer_name  = (
            request_data.get("required", {}).get("customer_name") or
            request_data.get("customer_name") or
            customer_email
        )

        # ── Get detected language from DB ────────────────────────────
        lang_meta     = shipment_doc.get("language_metadata", {}) if shipment_doc else {}
        detected_lang = (lang_meta.get("detected_language") or "en") if isinstance(lang_meta, dict) else "en"

        # 3. Build quote email (always in English first)
        all_fields = REQUIRED_FIELDS + OPTIONAL_FIELDS
        email_body = build_email(
            email_type    = "pricing",
            customer_name = customer_name,
            request_id    = request_id,
            pricing       = pricing_data,
            request_data  = request_data,
            all_fields    = all_fields,
            lang          = detected_lang,
        )

        # 4. Translate email body + subject if needed
        out_subject = f"LogiAI Quotation — {request_id}: {pricing_data.transport_mode or ''}"
        if detected_lang != "en":
            logger.info(f"[pricing_tools] Translating pricing email to '{detected_lang}' for {customer_email}")
            email_body  = translate_to_language(email_body, detected_lang)
            out_subject = translate_text_to_language(out_subject, detected_lang)

        # 5. Send email to customer
        outgoing_message_id = send_email(
            to         = customer_email,
            subject    = out_subject,
            body_html  = email_body,
            request_id = request_id
        )

        # 6. Check for existing pricing and merge if needed
        existing_pricing_list = shipment_doc.get("pricing_details", [])
        if existing_pricing_list:
            logger.debug(f"Found existing pricing, merging with new pricing")
            existing_pricing = PricingSchema(**existing_pricing_list[0])
            pricing_data = merge_pricing_data(existing_pricing, pricing_data)
            logger.debug(f"Pricing merged successfully")
        else:
            logger.debug(f"No existing pricing, using new pricing as-is")

        # 7. Log interaction
        outgoing_msg = Message(
            message_id   = outgoing_message_id,
            sender_email = settings.GMAIL_ADDRESS,
            sender_type  = "system",
            direction    = "outgoing",
            subject      = out_subject,
            body         = f"Quotation sent to customer. Transport Mode: {pricing_data.transport_mode}",
            received_at  = datetime.utcnow()
        )

        # 8. Update database
        await push_message_log(
            request_id      = request_id,
            message         = outgoing_msg.model_dump(),
            sent_message_id = outgoing_message_id,
            status          = "QUOTED"
        )
        
        await set_pricing_details(
            request_id   = request_id,
            pricing_data = pricing_data.model_dump()
        )

        logger.info(f"[pricing_tools] Quote sent for {request_id} to {customer_email} | lang={detected_lang}")
        
        return f"✅ Pricing quote sent to {customer_email} | msg_id={outgoing_message_id} | status=QUOTED"

    except Exception as e:
        logger.error(f"[pricing_tools] Error processing pricing: {e}")
        return f"❌ Failed to send pricing quote: {str(e)}"