import os
from agent.state import AgentState
from core.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import ValidationResult
from services.extraction_service import extract_fields, extract_missing_fields


def _compute_validation(required_data: dict) -> ValidationResult:
    """
    Checks which required fields are still None.
    Saves them into ValidationResult.missing_fields.
    """
    missing_fields = [
        field for field in REQUIRED_FIELDS
        if required_data.get(field) is None
    ]
    return ValidationResult(
        is_valid=len(missing_fields) == 0,
        missing_fields=missing_fields,
    )


# node function

def extraction_node(state: AgentState) -> dict:
    """
    Handles two intents:

    new_request:
        - Calls LLM to extract ALL fields from the email
        - Splits into required and optional
        - Computes ValidationResult — missing_fields saved to state
        - Returns request_data, validation_result, status

    missing_information:
        - Reads missing_fields from state (saved from DB on first extraction)
        - Calls LLM with ONLY those missing fields — focused extraction
        - Merges new values into existing request_data from state
        - Re-computes ValidationResult
        - missing_fields now only contains STILL missing fields
        - Returns updated request_data, validation_result, status
    """
    intent = state.get("intent")
    subject = state.get("translated_subject", "")
    body = state.get("translated_body", "")

    print("\n" + "=" * 60)
    print(f"[extraction_node] Intent: {intent}")
    print("=" * 60)

    # ── new_request ──────────────────────────────────────────
    if intent == "new_request":
        try:
            # Step 1 — Extract ALL fields via LLM
            schema = extract_fields(subject, body)
            schema_dict = schema.model_dump()

            # Step 2 — Split into required and optional
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

            # Step 3 — Compute ValidationResult
            # missing_fields saved into ValidationResult.missing_fields → goes to DB
            validation_result = _compute_validation(required_data)

            _print_extraction_result(subject, schema_dict, validation_result)

            return {
                "request_data":      request_data,
                "validation_result": validation_result,
            }

        except Exception as e:
            print(f"[extraction_node] ❌ Extraction error: {e}")
            return {"status": "ERROR"}

    # ── missing_information ──────────────────────────────────
    elif intent == "missing_information":
        try:
            # Step 1 — Read existing request_data from state
            # Keep all previously extracted values — don't lose them
            existing = state.get("request_data", {})
            required_data = dict(existing.get("required", {
                field: None for field in REQUIRED_FIELDS
            }))
            optional_data = dict(existing.get("optional", {}))

            # Step 2 — Read missing_fields from state
            # These were saved to DB on first extraction — use them as the target
            prev_validation = state.get("validation_result")
            missing_fields = (
                prev_validation.missing_fields
                if prev_validation else list(REQUIRED_FIELDS)
            )

            print(f"[extraction_node] Extracting only missing fields: {missing_fields}")

            # Step 3 — Extract ONLY the missing fields from the reply email
            # Focused extraction — LLM only looks for what's actually missing
            newly_extracted = extract_missing_fields(subject, body, missing_fields)

            print(f"[extraction_node] Newly extracted: {newly_extracted}")

            # Step 4 — Merge new values into existing required and optional data
            for field, value in newly_extracted.items():
                if field in REQUIRED_FIELDS:
                    required_data[field] = value
                elif field in OPTIONAL_FIELDS:
                    optional_data[field] = value

            request_data = {
                "required": required_data,
                "optional": optional_data,
            }

            # Step 5 — Re-compute ValidationResult
            # missing_fields now only contains STILL missing fields
            validation_result = _compute_validation(required_data)

            print(f"[extraction_node] Still missing : {validation_result.missing_fields}")
            print(f"[extraction_node] Complete      : {validation_result.is_valid}")

            return {
                "request_data":      request_data,
                "validation_result": validation_result,
            }

        except Exception as e:
            print(f"[extraction_node] ❌ Update error: {e}")
            return {"status": "ERROR"}

    # ── unknown intent ───────────────────────────────────────
    else:
        print("[extraction_node] Skipping — intent not handled here.")
        return {}


# console results

def _print_extraction_result(
    subject: str,
    schema_dict: dict,
    validation_result: ValidationResult,
) -> None:
    print("\n" + "=" * 60)
    print("[extraction_node] RESULT")
    print(f"  Subject : {subject.strip() or '(no subject)'}")
    print(f"  Status  : {'✅ Complete' if validation_result.is_valid else '⚠️  Missing fields'}")

    print("\n  ── Required fields ──")
    for field in REQUIRED_FIELDS:
        value = schema_dict.get(field)
        status = "✅" if value is not None else "❌"
        print(f"    {status} {field}: {value}")

    print("\n  ── Optional fields ──")
    for field in OPTIONAL_FIELDS:
        value = schema_dict.get(field)
        status = "✅" if value is not None else "➖"
        print(f"    {status} {field}: {value}")

    if validation_result.missing_fields:
        print(f"\n  Missing required: {validation_result.missing_fields}")
    print("=" * 60)
