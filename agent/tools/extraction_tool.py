"""
agent/tools/extraction_tool.py

Optimized tool-calling:
- Tools fetch the email content directly from MongoDB using request_id.
- No large body strings are passed to the LLM 'Brain'.
- Saves memory, tokens, and improves reliability for large emails.
- PDF/Excel Cloudinary upload is handled in parse_node (not here).
"""

import logging
from langchain_core.tools import tool

from config.constants              import REQUIRED_FIELDS, OPTIONAL_FIELDS
from services.ai.extraction_service import extract_fields, extract_missing_fields
from services.shipment.shipment_service import update_shipment, find_by_request_id

logger = logging.getLogger(__name__)


def _compute_validation(required_data: dict) -> dict:
    """
    Checks which required fields are still None.
    Returns a dict with is_valid and missing_fields.
    """
    missing_fields = [
        field for field in REQUIRED_FIELDS
        if required_data.get(field) is None
    ]
    return {
        "is_valid":       len(missing_fields) == 0,
        "missing_fields": missing_fields,
    }


@tool
async def extract_shipment_fields(request_id: str) -> dict:
    """
    Extracts ALL shipment fields from a new shipment request email.
    Reads the email body from the database using request_id.
    Saves extracted data and validation result to database automatically.

    Call this first for any new_request intent.
    CRITICAL DATA TYPE RULES:
    - STRING fields: Always use quotes "value"
    - INTEGER fields: Use numbers without quotes 123
    - FLOAT fields: Use decimal numbers 123.45
    - BOOLEAN fields: Use true/false (no quotes)
    - NULL values: Use null (not "null" or None)

    REQUIRED FIELDS (STRING - always in quotes):
    - customer_name: "Alpine Medical Supplies GmbH"
    - customer_street_number: "5" ← STRING not number
    - customer_zip_code: "80331" ← STRING not number
    - customer_country: "Germany"
    - origin_zip_code: "20457" ← STRING not number
    - origin_city: "Hamburg"
    - origin_country: "Germany"
    - destination_zip_code: "2100" ← STRING not number
    - destination_city: "Copenhagen"
    - destination_country: "Denmark"
    - incoterm: "DDP"
    - package_type: "Package"
    - container_type: "20' High Cube"
    - transport_mode: "Road"
    - shipment_type: "LCL"

    REQUIRED FIELDS (NUMERIC - no quotes):
    - quantity: 45 ← INTEGER

    REQUIRED FIELDS (WEIGHT/DIMENSION - string with unit):
    - cargo_weight: "2600 kg" ← STRING with unit
    - volume: "14 CBM"        ← STRING with unit
    - length: "1.2 m"         ← STRING with unit
    - height: "1.5 m"         ← STRING with unit
    - width: "1.0 m"          ← STRING with unit

    OPTIONAL FIELDS (STRING - always in quotes):
    - contact_person_name: "Laura Becker"
    - contact_person_email: "laura.becker@alpinemedical.de"
    - contact_person_phone: "+49 40 7788 2211"
    - customer_reference: "AMS-PO-2291"
    - origin_company: "Alpine Medical Warehouse"
    - origin_street_number: "12" ← STRING not number
    - destination_company: "Nordic Health Distribution"
    - destination_street_number: "48" ← STRING not number
    - description_of_goods: "Medical diagnostic equipment"
    - additional_information: "Handle with care"
    - temperature: "Ambient" (can be string or number)

    OPTIONAL FIELDS (BOOLEAN - no quotes):
    - stackable: true
    - dangerous: false

    CRITICAL EXAMPLES:
    ✅ CORRECT:
    {
    "customer_street_number": "5",
    "quantity": 45,
    "cargo_weight": 2600.0,
    "stackable": true
    }

    ❌ WRONG:
    {
    "customer_street_number": 5,
    "quantity": "45",
    "cargo_weight": "2600.0",
    "stackable": "true"
    }

    FIELD MAPPING GUIDE:
    - "Customer Street Number: 5" → "customer_street_number": "5"
    - "Origin Street Number: 12" → "origin_street_number": "12"
    - "Destination Street Number: 48" → "destination_street_number": "48"
    - "Quantity: 45" → "quantity": 45
    - "Cargo Weight: 2600 kg" → "cargo_weight": "2600 kg"
    - "Volume: 14 CBM" → "volume": "14 CBM"
    - "Stackable: Yes" → "stackable": true
    - "Dangerous: No" → "dangerous": false

    REMEMBER:
    - Street numbers, zip codes, phone numbers = STRINGS (with quotes)
    - Quantities, weights, dimensions = NUMBERS (no quotes)
    - Yes/No, True/False = BOOLEANS (true/false)
    - Missing information = null

    Args:
        request_id: The specific shipment REQ-ID to process.

    Returns:
        is_valid: True if all required fields were found.
        missing_fields: list of required fields still needed.
    """

    # Step 1 — Read email body from MongoDB (avoiding LLM context bloat)
    shipment = await find_by_request_id(request_id)
    if not shipment:
        logger.error("[extraction_tool] Shipment not found: %s", request_id)
        return {"is_valid": False, "missing_fields": list(REQUIRED_FIELDS)}

    email_subject = shipment.translated_subject or shipment.subject or ""
    email_body    = shipment.translated_body or shipment.body or ""

    logger.info("[extraction_tool] Extracting all fields for %s", request_id)

    # Step 2 — Extract ALL fields via LLM
    try:
        schema      = extract_fields(email_subject, email_body)
        schema_dict = schema.model_dump()
    except Exception as e:
        logger.error("[extraction_tool] LLM extraction failed: %s", e)
        return {"is_valid": False, "missing_fields": list(REQUIRED_FIELDS)}

    # Step 3 — Split into required and optional
    required_data = {
        field: schema_dict.get(field)
        for field in REQUIRED_FIELDS
    }
    optional_data = {
        field: schema_dict.get(field)
        for field in OPTIONAL_FIELDS
        if schema_dict.get(field) is not None
    }

    request_data = {
        "required": required_data,
        "optional": optional_data,
    }

    # Step 4 — Compute validation
    validation = _compute_validation(required_data)

    # Step 5 — Save results to MongoDB
    await update_shipment(request_id, {
        "request_data":      request_data,
        "validation_result": validation,
        "status":            "NEW",
    })

    _log_extraction_result(email_subject, schema_dict, validation)

    logger.info(
        "[extraction_tool] Done | request_id=%s | is_valid=%s | missing=%s",
        request_id, validation["is_valid"], validation["missing_fields"]
    )

    return {
        "is_valid":       validation["is_valid"],
        "missing_fields": validation["missing_fields"],
    }


@tool
async def extract_missing_field_values(
    request_id:     str,
    missing_fields: list,
) -> dict:
    """
    Extracts ONLY specific missing fields from a customer reply email.
    Reads the reply email body from the database using request_id.
    Merges new values with existing data and saves back to database.

    Call this for missing_information intent when customer has replied.

    Args:
        request_id:     The specific shipment REQ-ID.
        missing_fields: The list of field names still needed (from state).

    Returns:
        still_missing: list of fields still missing after this attempt.
        is_valid: True if everything is now complete.
    """

    # Step 1 — Read reply email and existing data from MongoDB
    shipment = await find_by_request_id(request_id)
    if not shipment:
        logger.error("[extraction_tool] Shipment not found: %s", request_id)
        return {"is_valid": False, "still_missing": missing_fields}

    email_subject = shipment.translated_subject or shipment.subject or ""
    email_body    = shipment.translated_body or shipment.body or ""

    # Step 2 — Load existing extracted data from MongoDB
    existing      = shipment.get("request_data", {})
    required_data = dict(existing.get("required", {
        field: None for field in REQUIRED_FIELDS
    }))
    optional_data = dict(existing.get("optional", {}))

    logger.info("[extraction_tool] Focused extraction for %s", request_id)

    # Step 3 — Focused extraction
    try:
        newly_extracted = extract_missing_fields(email_subject, email_body, missing_fields)
        logger.info("[extraction_tool] Newly extracted: %s", newly_extracted)
    except Exception as e:
        logger.error("[extraction_tool] Focused extraction failed: %s", e)
        return {"is_valid": False, "still_missing": missing_fields}

    # Step 4 — Merge new values into existing data
    for field, value in newly_extracted.items():
        if value is not None:
            if field in REQUIRED_FIELDS:
                required_data[field] = value
            elif field in OPTIONAL_FIELDS:
                optional_data[field] = value

    request_data = {
        "required": required_data,
        "optional": optional_data,
    }

    # Step 5 — Re-compute validation
    validation = _compute_validation(required_data)

    # Step 6 — Save merged data back to MongoDB
    await update_shipment(request_id, {
        "request_data":      request_data,
        "validation_result": validation,
    })

    return {
        "still_missing": validation["missing_fields"],
        "is_valid":      validation["is_valid"],
    }


def _log_extraction_result(subject: str, schema_dict: dict, validation: dict) -> None:
    """Log extraction results for debugging."""
    logger.info("=" * 60)
    logger.info("[extraction_tool] RESULT")
    logger.info(f"Subject : {subject.strip() or '(no subject)'}")
    logger.info(f"Status  : {'Complete' if validation['is_valid'] else 'Missing fields'}")

    logger.info("── Required fields ──")
    for field in REQUIRED_FIELDS:
        value  = schema_dict.get(field)
        status = "✅" if value is not None else "❌"
        logger.info(f"{status} {field}: {value}")

    logger.info("── Optional fields ──")
    for field in OPTIONAL_FIELDS:
        value  = schema_dict.get(field)
        status = "✅" if value is not None else "➖"
        logger.info(f"{status} {field}: {value}")

    if validation["missing_fields"]:
        logger.info(f"Missing required: {validation['missing_fields']}")
    logger.info("=" * 60)