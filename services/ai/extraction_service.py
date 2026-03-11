import json
import os
from dotenv import load_dotenv
from groq import Groq
from pydantic import ValidationError
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
import logging

logger = logging.getLogger(__name__)

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL")

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

Rules:
1. Extract only values explicitly mentioned.
2. shipment_type = LCL / FCL / AIR — NEVER put these in container_type
3. container_type = physical container size only (e.g. "40' GP", "20' High Cube")
4. quantity must be integer
5. weights and dimensions must be float
6. stackable / dangerous must be boolean
7. Convert written numbers to digits: "ten" → 10.0, "twenty" → 20.0
8. Unknown or missing fields → null
9. CRITICAL — for transport_mode, package_type, shipment_type, container_type, incoterm:
   Use ONLY the exact string from the allowed list. Do NOT paraphrase or extend.
   BAD: "Sea Freight" → GOOD: "Sea"
   BAD: "20FT Standard Container" → GOOD: "20' GP"
   BAD: "Pallet" → GOOD: "Pallets"
   BAD: "air freight" → GOOD: "Air"
   If no allowed value fits closely enough → null

Return ONLY JSON in this format:
{_JSON_FORMAT}
""".strip()


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
    body = (email_body    or "").strip()

    if not subject and not body:
        raise ValueError("Email subject and body are empty.")

    email_content = f"Subject: {subject}\n\nBody:\n{body}"

    try:
        response = client.chat.completions.create(
            model=EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Extract logistics shipment data:\n\n{email_content}",
                },
            ],
            temperature=0.0,
            max_tokens=1024,
        )

        raw_text = response.choices[0].message.content.strip()
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw_text)

        return ExtractionSchema(**parsed)

    except json.JSONDecodeError as e:
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

    Only sends the missing field names to the LLM — not all fields.
    This is more focused and accurate than re-extracting everything.

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

    # Build a focused prompt with only the missing fields
    missing_format = json.dumps({field: None for field in missing_fields}, indent=2)

    # Build format with ALL fields (not just missing ones)
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

Rules:
1. Extract ALL values explicitly mentioned in the email (not just the missing fields)
2. shipment_type = LCL / FCL / AIR — NEVER put these in container_type
3. container_type = physical container size only (e.g. "40' GP", "20' High Cube")
4. quantity must be integer
5. weights and dimensions must be float
6. stackable / dangerous must be boolean
7. Convert written numbers to digits: "ten" → 10.0, "twenty" → 20.0
8. If a field is not mentioned → null

Return JSON with ALL fields (set to null if not mentioned):
{all_fields_format}
""".strip()

    try:
        response = client.chat.completions.create(
            model=EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": focused_prompt},
                {
                    "role": "user",
                    "content": f"Extract fields from this reply (prioritize the missing fields but also extract any other fields mentioned):\n\n{email_content}",
                },
            ],
            temperature=0.0,
            max_tokens=1024,  # Increased from 512 since we're extracting more fields
            response_format={"type": "json_object"}  # Force JSON output
        )

        raw_text = response.choices[0].message.content
        if not raw_text:
            logger.error("LLM returned empty content")
            raise ValueError("LLM returned empty content")
        
        raw_text = raw_text.strip()
        logger.debug(f"LLM raw response: {raw_text[:200]}")
        
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        if not raw_text:
            logger.error("Empty after cleaning")
            raise ValueError("Empty response after cleaning markdown")
        
        parsed = json.loads(raw_text)

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
