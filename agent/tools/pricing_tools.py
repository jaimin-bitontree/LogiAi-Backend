"""
agent/tools/pricing_tools.py
"""

import logging
from langchain_core.tools import tool

from config.settings import settings
from config.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import PricingSchema
from services.ai.pricing_service import extract_pricing_data
from services.ai.language_service import translate_to_language
from services.email.email_sender import send_email
from services.email.email_template import build_email
from services.shipment.shipment_service import find_by_request_id, set_pricing_details, log_outgoing_message
from utils.language_helpers import get_detected_lang

logger = logging.getLogger(__name__)


def merge_pricing_data(existing_pricing: PricingSchema, new_pricing: PricingSchema) -> PricingSchema:
    existing_dict = existing_pricing.model_dump()
    new_dict      = new_pricing.model_dump()
    merged_dict   = {}
    for field, new_value in new_dict.items():
        if new_value is not None and new_value != "" and new_value != []:
            merged_dict[field] = new_value
        else:
            merged_dict[field] = existing_dict.get(field)
    return PricingSchema(**merged_dict)


def _translate_if_needed(email_body: str, detected_lang: str, customer_email: str) -> str:
    """Translate HTML email body to target language if not English."""
    if detected_lang == "en":
        return email_body
    logger.info(f"[pricing_tools] Translating pricing email to '{detected_lang}' for {customer_email}")
    return translate_to_language(email_body, detected_lang)


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

        # 1. Extract pricing data
        pricing_data, _ = extract_pricing_data(pricing_email_body)
        if not pricing_data:
            return {"success": False, "error": "Failed to extract pricing data from email"}

        # 2. Get shipment from DB
        shipment_doc = await find_by_request_id(request_id)
        if not shipment_doc:
            return {"success": False, "error": f"Shipment {request_id} not found"}

        customer_email = shipment_doc.customer_email
        request_data   = shipment_doc.request_data or {}
        customer_name  = (
            request_data.get("required", {}).get("customer_name") or
            request_data.get("customer_name") or
            customer_email
        )

        # 3. Get detected language from DB
        detected_lang = get_detected_lang(shipment_doc)

        # 4. Build email (English first)
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

        # 5. Subject kept as-is — never translated to preserve "Quotation" and REQ ID
        out_subject = f"LogiAI Quotation — {request_id}: {pricing_data.transport_mode or ''}"

        # 6. Translate body only if needed
        email_body = _translate_if_needed(email_body, detected_lang, customer_email)

        # 7. Send to customer
        outgoing_message_id = send_email(
            to         = customer_email,
            subject    = out_subject,
            body_html  = email_body,
            request_id = request_id,
        )

        # 8. Merge with existing pricing if any
        existing_pricing_list = shipment_doc.pricing_details or []
        if existing_pricing_list:
            pricing_data = merge_pricing_data(existing_pricing_list[0], pricing_data)

        # 9. Log + update DB
        await log_outgoing_message(
            request_id = request_id,
            message_id = outgoing_message_id,
            subject    = out_subject,
            body       = f"Quotation sent. Transport Mode: {pricing_data.transport_mode}",
            status     = "QUOTED",
        )
        await set_pricing_details(request_id=request_id, pricing_data=pricing_data.model_dump())

        logger.info(f"[pricing_tools] Quote sent for {request_id} to {customer_email} | lang={detected_lang}")
        return f"✅ Pricing quote sent to {customer_email} | msg_id={outgoing_message_id} | status=QUOTED"

    except Exception as e:
        logger.error(f"[pricing_tools] Error processing pricing: {e}")
        return f"❌ Failed to send pricing quote: {str(e)}"
