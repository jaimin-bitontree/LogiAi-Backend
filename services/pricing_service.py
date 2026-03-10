import json
import logging
from typing import Optional
from groq import Groq
from config import settings
from models.shipment import PricingSchema

logger = logging.getLogger(__name__)
client = Groq(api_key=settings.GROQ_API_KEY)

PRICING_SYSTEM_PROMPT = """
You are a logistics pricing assistant. Extract detailed freight quotation details from operator emails.

CRITICAL RULES:
1. ALL numeric values (amounts, rates, weights, volumes) MUST be strings, not numbers
   - Correct: "1680", "18200", "32.5"
   - Wrong: 1680, 18200, 32.5
2. Currency codes must be 3-letter strings (USD, EUR, GBP, etc.)
3. If a field is not found, use null (not empty string)
4. Extract ALL charges mentioned in the email

JSON Schema Structure:
{
  "request_id": "string or null - The REQ-YYYY-XXXXXXXXXX ID from email",
  "subject": "string or null - Email subject line",
  "greeting": "string or null - Opening greeting text",
  "transport_mode": "string or null - Sea/Air/Road/Rail",
  "pricing_type": "string or null - FCL/LCL/AIR",
  "shipment_details": {
    "pol": "string or null - Port of Loading",
    "pod": "string or null - Port of Discharge",
    "cargo_type": "string or null - Type of cargo",
    "container_type": "string or null - e.g. 20' GP, 40' HC",
    "weight_dimensions": "string or null - Weight and dimensions",
    "incoterm": "string or null - CIF, FOB, EXW, etc.",
    "special_requirements": "string or null - Any special notes",
    "chargeable_weight": "string or null - Weight as STRING",
    "volume": "string or null - Volume as STRING"
  },
  "main_freight_charges": [
    {
      "description": "string - Charge name",
      "rate": "string or null - Rate as STRING",
      "basis": "string or null - Per container, per kg, etc.",
      "amount": "string - Amount as STRING (REQUIRED)",
      "currency": "string - 3-letter code (REQUIRED)"
    }
  ],
  "origin_charges": [
    {
      "description": "string",
      "rate": "string or null",
      "basis": "string or null",
      "amount": "string - Amount as STRING",
      "currency": "string"
    }
  ],
  "destination_charges": [
    {
      "description": "string",
      "rate": "string or null",
      "basis": "string or null",
      "amount": "string - Amount as STRING",
      "currency": "string"
    }
  ],
  "additional_charges": [
    {
      "description": "string",
      "rate": "string or null",
      "basis": "string or null",
      "amount": "string - Amount as STRING",
      "currency": "string"
    }
  ],
  "payment_terms": {
    "validity": "string or null - Quote validity period",
    "conditions": "string or null - Payment conditions",
    "payment_method": "string or null - Payment method"
  },
  "calculation_notes": "string or null - Any additional notes",
  "closing": "string or null - Closing remarks"
}

EXAMPLES:
- If email says "Ocean Freight: USD 1,680" → {"description": "Ocean Freight", "amount": "1680", "currency": "USD"}
- If email says "Weight: 18,200 kg" → {"chargeable_weight": "18200"}
- If email says "Volume: 32 CBM" → {"volume": "32"}

Respond ONLY with valid JSON matching the schema above.
"""

def extract_pricing_data(email_body: str) -> tuple[Optional[PricingSchema], Optional[str]]:
    """
    Calls Groq LLM to extract structured pricing details and request_id from raw text.
    
    Returns:
        tuple: (PricingSchema or None, request_id or None)
        
    Raises:
        ValueError: If email body is empty or LLM returns invalid data
        RuntimeError: If LLM API call fails
    """
    if not email_body or not email_body.strip():
        raise ValueError("Empty email body provided for pricing extraction")
    
    try:
        logger.debug(f"[pricing_service] extract_pricing_data called with {len(email_body)} chars")
        logger.debug(f"[pricing_service] Using model: {settings.EXTRACTION_MODEL}")
        
        response = client.chat.completions.create(
            model=settings.EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": PRICING_SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract pricing and Request ID from this email:\n\n{email_body}"}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        logger.debug(f"[pricing_service] LLM raw response: {content[:500]}...")
        
        data = json.loads(content)
        request_id = data.pop("request_id", None)
        
        logger.debug(f"[pricing_service] Parsed data keys: {list(data.keys())}")
        logger.debug(f"[pricing_service] Extracted request_id: {request_id}")
        
        pricing_schema = PricingSchema(**data)
        logger.debug(f"[pricing_service] PricingSchema created successfully")
        
        return pricing_schema, request_id

    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}")
    except KeyError as e:
        raise ValueError(f"Missing expected field in LLM response: {e}")
    except ValueError as e:
        raise ValueError(f"Invalid pricing data returned by LLM: {e}")
    except Exception as e:
        raise RuntimeError(f"Pricing extraction failed: {e}")
    finally:
        logger.debug(f"[pricing_service] extract_pricing_data() | body: '{email_body[:100]}...')")
