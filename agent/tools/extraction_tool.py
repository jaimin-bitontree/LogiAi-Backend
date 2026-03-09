"""
agent/tools/extraction_tool.py

Optimized tool-calling:
- Tools fetch the email content directly from MongoDB using request_id.
- No large body strings are passed to the LLM 'Brain'.
- Saves memory, tokens, and improves reliability for large emails.
"""

import logging
from langchain_core.tools import tool

from core.constants              import REQUIRED_FIELDS, OPTIONAL_FIELDS
from services.extraction_service import extract_fields, extract_missing_fields
from api.shipment_service        import update_shipment_data, get_shipment_by_request_id

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

    Args:
        request_id: The specific shipment REQ-ID to process.

    Returns:
        is_valid: True if all required fields were found.
        missing_fields: list of required fields still needed.
    """

    # Step 1 — Read email body from MongoDB (avoiding LLM context bloat)
    shipment = await get_shipment_by_request_id(request_id)
    if not shipment:
        logger.error("[extraction_tool] Shipment not found: %s", request_id)
        return {"is_valid": False, "missing_fields": list(REQUIRED_FIELDS)}

    email_subject = shipment.get("translated_subject") or shipment.get("subject", "")
    email_body    = shipment.get("translated_body")    or shipment.get("body", "")

    logger.info("[extraction_tool] Extracting all fields for %s", request_id)

    # Step 2 — Extract ALL fields via LLM (still uses configured 8B model internally)
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
    # This keeps DB in sync so email tools see the latest data
    await update_shipment_data({
        "request_id":        request_id,
        "request_data":      request_data,
        "validation_result": validation,
        "status":            "NEW",
    })

    _print_extraction_result(email_subject, schema_dict, validation)

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
    shipment = await get_shipment_by_request_id(request_id)
    if not shipment:
        logger.error("[extraction_tool] Shipment not found: %s", request_id)
        return {"is_valid": False, "still_missing": missing_fields}

    email_subject = shipment.get("translated_subject") or shipment.get("subject", "")
    email_body    = shipment.get("translated_body")    or shipment.get("body", "")

    # Step 2 — Load existing extracted data from MongoDB to ensure merge accuracy
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
    await update_shipment_data({
        "request_id":        request_id,
        "request_data":      request_data,
        "validation_result": validation,
    })

    return {
        "still_missing": validation["missing_fields"],
        "is_valid":      validation["is_valid"],
    }


def _print_extraction_result(subject: str, schema_dict: dict, validation: dict) -> None:
    """Console output for debugging extraction results."""
    print("\n" + "=" * 60)
    print("[extraction_tool] RESULT")
    print(f"  Subject : {subject.strip() or '(no subject)'}")
    print(f"  Status  : {'✅ Complete' if validation['is_valid'] else '⚠️  Missing fields'}")

    print("\n  ── Required fields ──")
    for field in REQUIRED_FIELDS:
        value  = schema_dict.get(field)
        status = "✅" if value is not None else "❌"
        print(f"    {status} {field}: {value}")

    print("\n  ── Optional fields ──")
    for field in OPTIONAL_FIELDS:
        value  = schema_dict.get(field)
        status = "✅" if value is not None else "➖"
        print(f"    {status} {field}: {value}")

    if validation["missing_fields"]:
        print(f"\n  Missing required: {validation['missing_fields']}")
    print("=" * 60)
