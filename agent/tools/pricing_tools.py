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
from models.shipment import Message
from services.ai.pricing_service import extract_pricing_data
from services.email.email_sender import send_email
from services.email.email_template import build_email
from services.shipment.shipment_service import push_message_log, get_shipment_by_request_id
from db.client import get_db

logger = logging.getLogger(__name__)


@tool
async def calculate_and_send_pricing(request_id: str, pricing_email_body: str) -> dict:
    """Calculate pricing from operator email and send quote to customer.
    
    Args:
        request_id: The shipment request ID
        pricing_email_body: Email body containing pricing information from operator
        
    Returns:
        Result with status and details
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
        request_data = shipment_doc.get("request_data", {})
        customer_name = (
            request_data.get("required", {}).get("customer_name") or
            request_data.get("customer_name") or
            customer_email
        )

        # 3. Build quote email
        all_fields = REQUIRED_FIELDS + OPTIONAL_FIELDS
        email_body = build_email(
            email_type="pricing",
            customer_name=customer_name,
            request_id=request_id,
            pricing=pricing_data,
            request_data=request_data,
            all_fields=all_fields
        )

        # 4. Send email to customer
        out_subject = f"LogiAI Quotation — {request_id}: {pricing_data.transport_mode or ''}"
        
        outgoing_message_id = send_email(
            to=customer_email,
            subject=out_subject,
            body_html=email_body,
            request_id=request_id
        )

        # 5. Log interaction
        outgoing_msg = Message(
            message_id=outgoing_message_id,
            sender_email=settings.GMAIL_ADDRESS,
            sender_type="system",
            direction="outgoing",
            subject=out_subject,
            body=f"Quotation sent to customer. Transport Mode: {pricing_data.transport_mode}",
            received_at=datetime.utcnow()
        )

        # 6. Update database
        await push_message_log(
            request_id=request_id,
            message=outgoing_msg.model_dump(),
            sent_message_id=outgoing_message_id,
            status="QUOTED"
        )
        
        # Save pricing details
        db = get_db()
        await db.shipments.update_one(
            {"request_id": request_id},
            {"$push": {"pricing_details": pricing_data.model_dump()}}
        )

        logger.info(f"[pricing_tools] Quote sent for {request_id} to {customer_email}")
        
        return {
            "success": True,
            "message": f"Pricing quote sent to {customer_email}",
            "pricing_data": pricing_data.model_dump(),
            "message_id": outgoing_message_id
        }

    except Exception as e:
        logger.error(f"[pricing_tools] Error processing pricing: {e}")
        return {"success": False, "error": str(e)}