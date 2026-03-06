import json
import os
from typing import Optional
from dotenv import load_dotenv
from groq import Groq
from pydantic import ValidationError
from agent.state import AgentState
from schemas.extraction_schema import ExtractionSchema
from core.constants import (
    INCOTERMS,
    PACKAGE_TYPES,
    SHIPMENT_TYPES,
    TRANSPORT_MODES,
    CONTAINER_TYPES,
    REQUIRED_FIELDS,
    OPTIONAL_FIELDS,
)
from models.shipment import ValidationResult

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL")

# json format
_JSON_FORMAT = json.dumps(
    {field: None for field in ExtractionSchema.model_fields.keys()},
    indent=2
)

# System prompt
EXTRACTION_SYSTEM_PROMPT = f"""
You are a logistics data extraction engine for LogiAI.

Extract shipment information from emails.

Required fields:
{json.dumps(REQUIRED_FIELDS, indent=2)}

Optional fields:
{json.dumps(OPTIONAL_FIELDS, indent=2)}

Allowed values:
incoterm: {json.dumps(INCOTERMS)}
package_type: {json.dumps(PACKAGE_TYPES)}
shipment_type: {json.dumps(SHIPMENT_TYPES)}
transport_mode: {json.dumps(TRANSPORT_MODES)}
container_type: {json.dumps(CONTAINER_TYPES)}

Rules:
1. Extract only values explicitly mentioned.
2. shipment_type = LCL/FCL/AIR
3. container_type = container size (20' GP, 40' GP)
4. quantity must be integer
5. weights and dimensions must be float
6. stackable/dangerous must be boolean
7. unknown fields → null

Return ONLY JSON in this format:

{_JSON_FORMAT}
""".strip()


# LLM extraction function
def extract_fields(email_subject: str, email_body: str) -> ExtractionSchema:

    subject = (email_subject or "").strip()
    body = (email_body or "").strip()

    if not subject and not body:
        raise ValueError("Email subject and body are empty")

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

    except Exception as e:
        raise RuntimeError(f"Extraction failed: {e}")

    finally:
        print(f"[extraction_node] extract_fields() | subject: '{subject[:50]}'")


# node function
def extraction_node(state: AgentState) -> dict:
    """
    Handles:
    - new_request
    - missing_information
    """

    intent = state.get("intent")

    subject = state.get("translated_subject", "")
    body = state.get("translated_body", "")

    print("\n" + "=" * 60)
    print(f"[extraction_node] Intent: {intent}")
    print("=" * 60)

    # new request — extract all fields and validate
    if intent == "new_request":

        try:

            schema = extract_fields(subject, body)
            schema_dict = schema.model_dump()

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

            missing_fields = [
                f for f in REQUIRED_FIELDS
                if required_data.get(f) is None
            ]

            validation_result = ValidationResult(
                is_valid=len(missing_fields) == 0,
                missing_fields=missing_fields,
            )

            _print_extraction_result(subject, schema, validation_result)

            return {
                "request_data": request_data,
                "validation_result": validation_result,
                "status": "COMPLETED" if validation_result.is_valid else "MISSING_INFO",
            }

        except Exception as e:

            print(f"[extraction_node] ❌ Extraction error: {e}")

            return {
                "status": "ERROR"
            }

    # missing information — update state with any provided fields and re-validate
    elif intent == "missing_information":

        request_data = state.get("request_data", {})
        required_data = request_data.get("required", {})
        optional_data = request_data.get("optional", {})

        provided_fields = state.get("provided_fields", {})

        print(f"[extraction_node] Updating fields: {provided_fields}")

        for field, value in provided_fields.items():

            if field in required_data:
                required_data[field] = value

            elif field in OPTIONAL_FIELDS:
                optional_data[field] = value

        request_data = {
            "required": required_data,
            "optional": optional_data,
        }

        missing_fields = [
            f for f in REQUIRED_FIELDS
            if required_data.get(f) is None
        ]

        validation_result = ValidationResult(
            is_valid=len(missing_fields) == 0,
            missing_fields=missing_fields,
        )

        print("\n[extraction_node] STATE UPDATE")
        print(f"Missing fields: {missing_fields}")
        print(f"Completed: {validation_result.is_valid}")

        return {
            "request_data": request_data,
            "validation_result": validation_result,
            "status": "COMPLETED" if validation_result.is_valid else "MISSING_INFO",
        }
    # unknown intent — skip extraction
    else:
        print("[extraction_node] Unknown intent")
        return {"status": "SKIPPED"}


# console extraction result
def _print_extraction_result(
    subject: str,
    schema: ExtractionSchema,
    validation_result: ValidationResult,
):

    print("\n" + "=" * 60)
    print("[extraction_node] RESULT")
    print(f"Subject: {subject.strip()}")
    print(f"Status : {'COMPLETED' if validation_result.is_valid else 'MISSING_INFO'}")

    print("\nRequired Fields")

    for field in REQUIRED_FIELDS:

        value = getattr(schema, field, None)
        status = "✅" if value is not None else "❌"

        print(f"{status} {field}: {value}")

    print("\nOptional Fields")

    for field in OPTIONAL_FIELDS:

        value = getattr(schema, field, None)
        status = "✅" if value is not None else "➖"

        print(f"{status} {field}: {value}")

    if validation_result.missing_fields:
        print("\nMissing required fields:")
        print(validation_result.missing_fields)

    print("=" * 60)
