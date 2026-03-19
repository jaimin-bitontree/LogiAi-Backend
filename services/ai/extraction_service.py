import json
import logging
from google import genai
from pydantic import ValidationError
from config.settings import settings
from schemas.extraction_schema import ExtractionSchema
from config.constants import (
    INCOTERMS,
    PACKAGE_TYPES,
    SHIPMENT_TYPES,
    TRANSPORT_MODES,
    CONTAINER_TYPES,
    REQUIRED_FIELDS,
    OPTIONAL_FIELDS,
)

logger = logging.getLogger(__name__)

client = genai.Client(api_key=settings.GEMINI_API_KEY)

EXTRACTION_MODEL = settings.EXTRACTION_MODEL

# ===================================================
# JSON FORMAT — built directly from ExtractionSchema
# ===================================================

_JSON_FORMAT = json.dumps(
    {field: None for field in ExtractionSchema.model_fields.keys()},
    indent=2
)

# ===================================================
# SYSTEM PROMPT
# ===================================================

EXTRACTION_SYSTEM_PROMPT = f"""
You are a logistics data extraction engine for LogiAI.

Extract shipment information from emails.

Required fields:
{json.dumps(REQUIRED_FIELDS, indent=2)}

Optional fields:
{json.dumps(OPTIONAL_FIELDS, indent=2)}

Allowed values — copy EXACTLY from this list, no paraphrasing:
incoterm       : {json.dumps(INCOTERMS)}
package_type   : {json.dumps(PACKAGE_TYPES)}
shipment_type  : {json.dumps(SHIPMENT_TYPES)}
transport_mode : {json.dumps(TRANSPORT_MODES)}
container_type : {json.dumps(CONTAINER_TYPES)}

CRITICAL DATA TYPE RULES:
1. STRING fields (must be quoted strings):
   - customer_street_number: "5"
   - customer_zip_code: "12345"
   - origin_zip_code: "67890"
   - destination_zip_code: "54321"
   - All other text fields: customer_name, city, country, etc.

2. INTEGER fields (numbers without quotes):
   - quantity: 10 (NOT "10")

3. WEIGHT/DIMENSION fields — ALWAYS include the unit as a string:
   - cargo_weight: "4800 kg"  (NOT 4800)
   - volume: "22 CBM"         (NOT 22)
   - length: "1.2 m"          (NOT 1.2)
   - height: "1.5 m"          (NOT 1.5)
   - width: "1.0 m"           (NOT 1.0)
   If no unit is mentioned in the email, use the most common unit for that field:
   cargo_weight → kg, volume → CBM, length/height/width → m

4. BOOLEAN fields (true/false without quotes):
   - stackable: true (NOT "true")
   - dangerous: false (NOT "false")

Extraction Rules:
1. Extract only values explicitly mentioned.
2. shipment_type = LCL / FCL / AIR — NEVER put these in container_type
3. container_type = physical container size only (e.g. "40' GP", "20' High Cube")
4. Convert written numbers to digits: "ten" → "10 kg"
5. Unknown or missing fields → null
6. CRITICAL — for transport_mode, package_type, shipment_type, container_type, incoterm:
   Use ONLY the exact string from the allowed list. Do NOT paraphrase or extend.
   BAD: "Sea Freight" → GOOD: "Sea"
   BAD: "20FT Standard Container" → GOOD: "20' GP"
   BAD: "Pallet" → GOOD: "Pallets"
   BAD: "air freight" → GOOD: "Air"
   If no allowed value fits closely enough → null

EXAMPLES:
✅ CORRECT: {{"customer_street_number": "5", "quantity": 10, "cargo_weight": "4800 kg", "volume": "22 CBM", "length": "1.2 m", "stackable": true}}
❌ WRONG: {{"customer_street_number": 5, "quantity": "10", "cargo_weight": 4800, "volume": 22}}

Return ONLY a JSON object (not a list) in this format:
{_JSON_FORMAT}
""".strip()


def _safe_parse(raw_text: str) -> dict:
    """
    Safely parse LLM JSON response.
    Handles edge cases:
    - LLM returns a list instead of a dict → take first item
    - LLM wraps dict in a list → unwrap it
    """
    parsed = json.loads(raw_text)

    # If LLM returned a list, take the first item
    if isinstance(parsed, list):
        logger.warning(
            "[extraction_service] LLM returned a list instead of dict — "
            "taking first item"
        )
        if not parsed:
            raise ValueError("LLM returned empty list")
        parsed = parsed[0]

    # Final check — must be a dict
    if not isinstance(parsed, dict):
        raise ValueError(f"LLM returned unexpected type: {type(parsed)}")

    return parsed


def extract_fields(email_subject: str, email_body: str) -> ExtractionSchema:
    """
    Calls Groq LLM to extract ALL logistics fields from the email.
    Used for new_request intent.

    Args:
        email_subject: Email subject line
        email_body:    Email body text

    Returns:
        Validated ExtractionSchema object
    """
    subject = (email_subject or "").strip()
    body    = (email_body    or "").strip()

    if not subject and not body:
        raise ValueError("Email subject and body are empty.")

    email_content = f"Subject: {subject}\n\nBody:\n{body}"

    try:
        prompt = f"""{EXTRACTION_SYSTEM_PROMPT}

Extract logistics information from this email:

{email_content}"""
        
        response = client.models.generate_content(
            model=EXTRACTION_MODEL,
            contents=prompt
        )

        raw_text = response.text

        if not raw_text:
            logger.error("LLM returned empty content")
            raise ValueError("LLM returned empty content")

        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

        if not raw_text:
            logger.error("Empty after cleaning markdown")
            raise ValueError("Empty response after cleaning markdown")

        parsed = _safe_parse(raw_text)

        return ExtractionSchema(**parsed)

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        logger.debug(f"Raw text was: {raw_text if 'raw_text' in locals() else 'N/A'}")
        raise ValueError(f"Invalid JSON from LLM: {e}")
    except ValidationError as e:
        raise ValueError(f"Schema validation error: {e}")
    except ValueError:
        raise
    except Exception as e:
        raise RuntimeError(f"Extraction failed: {e}")
    finally:
        logger.debug(f"extract_fields() | subject: '{subject[:50]}'")


def extract_missing_fields(
    email_subject: str,
    email_body: str,
    missing_fields: list[str],
) -> dict:
    """
    Calls Groq LLM to extract ONLY the missing fields from a reply email.
    Used for missing_information intent.

    Args:
        email_subject:  Reply email subject
        email_body:     Reply email body
        missing_fields: List of field names still missing (from DB/state)

    Returns:
        Dict with only the newly extracted field values
    """
    subject = (email_subject or "").strip()
    body    = (email_body    or "").strip()

    if not subject and not body:
        raise ValueError("Email subject and body are empty.")

    if not missing_fields:
        return {}

    email_content = f"Subject: {subject}\n\nBody:\n{body}"

    all_fields_format = json.dumps(
        {field: None for field in REQUIRED_FIELDS + OPTIONAL_FIELDS},
        indent=2
    )

    focused_prompt = f"""
You are a logistics data extraction engine for LogiAI.

The customer was asked to provide these missing fields:
{json.dumps(missing_fields, indent=2)}

IMPORTANT: Extract the missing fields above, BUT ALSO extract any other shipment fields 
mentioned in the email (even if not requested). This ensures no information is lost.

All possible fields:
Required: {json.dumps(REQUIRED_FIELDS, indent=2)}
Optional: {json.dumps(OPTIONAL_FIELDS, indent=2)}

Allowed values:
incoterm       : {json.dumps(INCOTERMS)}
package_type   : {json.dumps(PACKAGE_TYPES)}
shipment_type  : {json.dumps(SHIPMENT_TYPES)}
transport_mode : {json.dumps(TRANSPORT_MODES)}
container_type : {json.dumps(CONTAINER_TYPES)}

CRITICAL DATA TYPE RULES:
1. STRING fields (must be quoted strings):
   - customer_street_number: "5"
   - customer_zip_code: "12345"
   - origin_zip_code: "67890"
   - destination_zip_code: "54321"
   - All other text fields: customer_name, city, country, etc.

2. INTEGER fields (numbers without quotes):
   - quantity: 10 (NOT "10")

3. WEIGHT/DIMENSION fields — ALWAYS include the unit as a string:
   - cargo_weight: "4800 kg"  (NOT 4800)
   - volume: "22 CBM"         (NOT 22)
   - length: "1.2 m"          (NOT 1.2)
   - height: "1.5 m"          (NOT 1.5)
   - width: "1.0 m"           (NOT 1.0)

4. BOOLEAN fields (true/false without quotes):
   - stackable: true (NOT "true")
   - dangerous: false (NOT "false")

Extraction Rules:
1. Extract ALL values explicitly mentioned in the email (not just the missing fields)
2. shipment_type = LCL / FCL / AIR — NEVER put these in container_type
3. container_type = physical container size only (e.g. "40' GP", "20' High Cube")
4. Convert written numbers to digits: "ten" → "10 kg"
5. If a field is not mentioned → null

Return ONLY a JSON object (not a list) with ALL fields (set to null if not mentioned):
{all_fields_format}
""".strip()

    try:
        prompt = f"""{focused_prompt}

Extract fields from this reply:

{email_content}"""
        
        response = client.models.generate_content(
            model=EXTRACTION_MODEL,
            contents=prompt
        )

        raw_text = response.text
        if not raw_text:
            logger.error("LLM returned empty content")
            raise ValueError("LLM returned empty content")

        raw_text = raw_text.strip()
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

        if not raw_text:
            logger.error("Empty after cleaning")
            raise ValueError("Empty response after cleaning markdown")

        parsed = _safe_parse(raw_text)

        # Return only non-null values
        return {k: v for k, v in parsed.items() if v is not None}

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        logger.debug(f"Raw text was: {raw_text if 'raw_text' in locals() else 'N/A'}")
        raise ValueError(f"Invalid JSON from LLM: {e}")
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise RuntimeError(f"Missing field extraction failed: {e}")
    finally:
        logger.debug(f"extract_missing_fields() | missing: {missing_fields}")