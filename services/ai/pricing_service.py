import json
import logging
from typing import Optional
from google import genai
from config.settings import settings
from models.shipment import PricingSchema

logger = logging.getLogger(__name__)
client = genai.Client(api_key=settings.GEMINI_API_KEY)

PRICING_SYSTEM_PROMPT = """
You are a logistics pricing assistant. Extract detailed freight quotation details from operator emails.

CRITICAL RULES:
1. ALL numeric values (amounts, rates, weights, volumes) MUST be strings, not numbers
   - Correct: "1680", "18200", "32.5"
   - Wrong: 1680, 18200, 32.5
2. Currency codes must be 3-letter strings (USD, EUR, GBP, etc.)
3. If a field is not found, use null (not empty string)
4. Extract ALL charges mentioned in the email
5. IMPORTANT: Look for patterns like "Amount: 210" and "Currency: EUR" - extract the values after the colon
  - ALL charge arrays must be empty lists [] if no charges found, NEVER null/None
- "main_freight_charges": [] (if no main charges found)
- "origin_charges": [] (if no origin charges found)  
- "destination_charges": [] (if no destination charges found)
- "additional_charges": [] (if no additional charges found)
- "shipment_details": {} (if no details found)
- "payment_terms": {} (if no terms found)
CHARGE EXTRACTION PATTERNS:
- "Description: Ocean Freight Hamburg → Mumbai" → description: "Ocean Freight Hamburg → Mumbai"
- "Amount: 210" → amount: "210" (extract number after "Amount:")
- "Currency: EUR" → currency: "EUR" (extract code after "Currency:")
- "Rate: 1385" → rate: "1385" (extract number after "Rate:")
- "Basis: Per Container" → basis: "Per Container" (extract text after "Basis:")

SECTION PATTERNS TO LOOK FOR:
- "Main Freight Charges" section
- "Origin Charges" section  
- "Destination Charges" section
- "Additional Charges" section
- "Payment Terms" section
- "Shipment Details" section

COMMON EMAIL FORMATS:
Format 1 (Line-by-line):
Description: Origin Terminal Handling Charge (THC)
Amount: 210
Currency: EUR

Format 2 (Inline):
Ocean Freight: USD 1,680

Format 3 (Mixed):
Description: BAF (Bunker Adjustment Factor)
Rate: 165
Basis: Per Container
Amount: 165
Currency: USD

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
      "amount": "string - Amount as STRING (REQUIRED - never null)",
      "currency": "string - 3-letter code (REQUIRED - never null)"
    }
  ],
  "origin_charges": [
    {
      "description": "string",
      "rate": "string or null",
      "basis": "string or null", 
      "amount": "string - Amount as STRING (REQUIRED - never null)",
      "currency": "string - 3-letter code (REQUIRED - never null)"
    }
  ],
  "destination_charges": [
    {
      "description": "string",
      "rate": "string or null",
      "basis": "string or null",
      "amount": "string - Amount as STRING (REQUIRED - never null)",
      "currency": "string - 3-letter code (REQUIRED - never null)"
    }
  ],
  "additional_charges": [
    {
      "description": "string",
      "rate": "string or null", 
      "basis": "string or null",
      "amount": "string - Amount as STRING (REQUIRED - never null)",
      "currency": "string - 3-letter code (REQUIRED - never null)"
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

EXTRACTION EXAMPLES:
Input: "Description: Origin Terminal Handling Charge (THC)\nAmount: 210\nCurrency: EUR"
Output: {"description": "Origin Terminal Handling Charge (THC)", "amount": "210", "currency": "EUR"}

Input: "Description: BAF (Bunker Adjustment Factor)\nRate: 165\nBasis: Per Container\nAmount: 165\nCurrency: USD"
Output: {"description": "BAF (Bunker Adjustment Factor)", "rate": "165", "basis": "Per Container", "amount": "165", "currency": "USD"}

Input: "Ocean Freight Hamburg → Mumbai: USD 1,385"
Output: {"description": "Ocean Freight Hamburg → Mumbai", "amount": "1385", "currency": "USD"}

CRITICAL: Never return null for "amount" or "currency" fields in charge items. Always extract these values as strings.

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
        
        prompt = f"""{PRICING_SYSTEM_PROMPT}

Extract pricing and Request ID from this email:

{email_body}"""
        
        response = client.models.generate_content(
            model=settings.EXTRACTION_MODEL,
            contents=prompt
        )

        content = response.text
        logger.debug(f"[pricing_service] LLM raw response: {content[:500]}...")
        
        # Clean markdown formatting
        content = content.replace("```json", "").replace("```", "").strip()
        
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
