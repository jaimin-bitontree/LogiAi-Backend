"""
agent/tools/spam_tools.py

Tool for handling spam/phishing emails.
Sends a polite rejection template to spam senders.
"""

import logging
from datetime import datetime
from langchain_core.tools import tool

from config.settings import settings
from models.shipment import Message
from services.email.email_sender import send_email
from services.email.email_template import build_email
from services.shipment.shipment_service import push_message_log

logger = logging.getLogger(__name__)


@tool
async def handle_spam_email(
    customer_email: str,
    subject: str,
) -> str:
    """
    Handles spam/phishing emails by sending a polite rejection template.
    
    Args:
        customer_email: Sender's email address
        subject: Original email subject
        
    Returns:
        Confirmation string with sent message ID
    """
    try:
        logger.info(f"[spam_tools] Processing spam email from {customer_email}")
        
        # 1. Build spam rejection email using template
        html = build_email(
            email_type="spam",
            customer_email=customer_email,
            subject=subject,
        )
        
        # 2. Send email
        out_subject = "Re: Your Email"
        sent_message_id = send_email(
            to=customer_email,
            subject=out_subject,
            body_html=html,
            request_id=""  # No request_id for spam
        )
        
        logger.info(f"[spam_tools] Spam rejection sent to {customer_email} | msg_id={sent_message_id}")
        
        return {
            "success" : True,
            "message" : "Successfully handled spam mail",
            "message_id": sent_message_id
            
        }
        
    except Exception as e:
        logger.error(f"[spam_tools] Error handling spam email: {e}")
        return {
        "success": False,
        "error": str(e)
    }
