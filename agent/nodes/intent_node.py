import json
import os
from typing import Optional
from enum import Enum
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel
from agent.state import AgentState
from core.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from models.shipment import ValidationResult

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


# ===================================================
# ENUMS & MODELS
# ===================================================

class EmailIntent(str, Enum):
    NEW_REQUEST = "new_request"
    STATUS_INQUIRY = "status_inquiry"
    CONFIRMATION = "confirmation"
    CANCELLATION = "cancellation"
    MISSING_INFORMATION = "missing_information"


class FieldDetail(BaseModel):
    field: str
    value: Optional[str] = None


class IntentResult(BaseModel):
    intent: EmailIntent
    confidence: float
    reason: str
    # missing_information
    request_id: Optional[str] = None
    provided_fields: Optional[list[FieldDetail]] = None


# ===================================================
# SYSTEM PROMPT
# ===================================================

INTENT_SYSTEM_PROMPT = f"""
You are an email intent classifier for a logistics platform called LogiAI.

You will receive an email with a Subject line and a Body.
Both the subject and body together form the full context — read BOTH carefully.
The subject alone may reveal the intent even if the body is short or vague.
Emails may be written as plain conversational paragraphs with no labels or structure.

Classify the given email into exactly ONE of these intents:

1. new_request - Sender wants a new shipment, pickup, or logistics service.
2. status_inquiry - Sender is asking about the status of an existing shipment/order.
3. confirmation - Sender is confirming a previously discussed shipment or booking.
4. cancellation - Sender wants to cancel an existing shipment or order.
5. missing_information - Email is too vague or missing critical logistics details.
                         If the email has NO origin, NO destination, NO quantity, and NO
                         item details — it MUST be missing_information even if it hints
                         at a future shipment.

ONLY when intent is missing_information, you MUST also:
1. Extract "request_id" — any shipment ID, order ID, tracking number, booking ref,
   or customer reference found anywhere in the email. If none found, set null.
2. Extract "provided_fields" — scan the email and list ONLY the fields that ARE
   mentioned with their values. Use these field names:
   {json.dumps(REQUIRED_FIELDS + OPTIONAL_FIELDS)}
   Only include fields that are clearly present. Do NOT include fields that are missing.

Respond ONLY in this exact JSON format, no extra text, no markdown:
{{
  "intent": "<new_request | status_inquiry | confirmation | cancellation | missing_information>",
  "confidence": <float 0.0 to 1.0>,
  "reason": "<one sentence explanation>",
  "request_id": "<extracted ID or null>",
  "provided_fields": [{{"field": "field_name", "value": "extracted value"}}]
}}

Note: "request_id" and "provided_fields" are ONLY populated when intent is
missing_information. For all other intents set both to null.
""".strip()


# ===================================================
# CORE FUNCTION
# ===================================================

def detect_intent(email_subject: str, email_body: str) -> IntentResult:
    """
    Detects the intent of a logistics email using Groq LLM.
    Expects TRANSLATED subject and body (always English).

    For missing_information intent also extracts:
      - request_id      : any reference ID found in the email
      - provided_fields : fields that ARE present in the email
        (missing fields are computed in intent_node, not here)
    """
    subject = (email_subject or "").strip()
    body = (email_body or "").strip()

    if not subject and not body:
        return IntentResult(
            intent=EmailIntent.MISSING_INFORMATION,
            confidence=1.0,
            reason="Email subject and body are both empty.",
            request_id=None,
            provided_fields=None,
        )

    email_content = f"Subject: {subject}\n\nBody:\n{body}" if subject else f"Body:\n{body}"

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Classify the intent of this email:\n\n{email_content}",
                },
            ],
            temperature=0.1,
            max_tokens=512,
        )

        raw_text = response.choices[0].message.content.strip()
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

        parsed = json.loads(raw_text)

        try:
            confidence = max(0.0, min(1.0, float(parsed["confidence"])))
        except (TypeError, ValueError):
            confidence = 0.0

        provided = None
        if parsed.get("provided_fields"):
            provided = [
                FieldDetail(field=f["field"], value=f.get("value"))
                for f in parsed["provided_fields"]
            ]

        return IntentResult(
            intent=EmailIntent(parsed["intent"]),
            confidence=confidence,
            reason=parsed["reason"],
            request_id=parsed.get("request_id"),
            provided_fields=provided,
        )

    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}")
    except KeyError as e:
        raise ValueError(f"Missing expected field in LLM response: {e}")
    except ValueError as e:
        raise ValueError(f"Invalid intent value returned by LLM: {e}")
    except Exception as e:
        raise RuntimeError(f"Intent detection failed: {e}")
    finally:
        print(f"[intent_node] detect_intent() | subject: '{subject[:50]}' | body: '{body[:50]}...'")


# ===================================================
# LANGGRAPH NODE
# ===================================================

def intent_node(state: AgentState) -> dict:
    translated_subject = state.get("translated_subject", "")
    translated_body = state.get("translated_body", "")

    result = detect_intent(translated_subject, translated_body)
    _print_intent_result(translated_subject, result)

    output = {"intent": result.intent.value}

    if result.intent == EmailIntent.MISSING_INFORMATION:
        request_data = {}
        if result.provided_fields:
            for f in result.provided_fields:
                if f.value is not None:
                    request_data[f.field] = f.value

        provided_keys = set(request_data.keys())
        missing_fields = [f for f in REQUIRED_FIELDS if f not in provided_keys]

        output["request_id"] = result.request_id
        output["request_data"] = request_data
        output["validation_result"] = ValidationResult(
            is_valid=len(missing_fields) == 0,
            missing_fields=missing_fields,
        )

    return output


# ===================================================
# CONSOLE PRINT HELPER
# ===================================================

def _print_intent_result(subject: str, result: IntentResult) -> None:
    print("\n" + "=" * 60)
    print("[intent_node] RESULT")
    print(f"  Subject    : {subject.strip() or '(no subject)'}")
    print(f"  Intent     : {result.intent.value}")
    print(f"  Confidence : {result.confidence:.2f}")
    print(f"  Reason     : {result.reason}")

    if result.intent == EmailIntent.MISSING_INFORMATION:
        print(f"  Request ID : {result.request_id or 'NOT FOUND'}")
        if result.provided_fields:
            print("  Provided   :")
            for f in result.provided_fields:
                print(f"    - {f.field}: {f.value}")
    print("=" * 60)


# ===================================================
# TEMPORARY TEST
# ===================================================

if __name__ == "__main__":

    test_emails = [
        ("Shipment Request - Chicago to Dallas",
         "Hi, we are SteelCore Manufacturing based out of Chicago and we need to move "
         "industrial conveyor belt parts to Dallas Texas. We have 3 pallets, 1500 kg total, "
         "120x80x100 cm each. Origin: 142 West Industrial Ave Chicago IL 60601. "
         "Destination: 300 Commerce Street Dallas TX 75201. "
         "Sea freight, FCL, EXW incoterm. Contact John Miller +1-312-555-0192."),

        ("Follow up on SHP-20948",
         "Hey, following up on shipment SHP-20948 from Miami to Atlanta sent Feb 20th. "
         "Still not received. Can you give us an ETA? Sarah Thompson, supply chain team."),

        ("Booking Confirmation BK-3821",
         "Confirming our booking BK-3821, invoice INV-992, agreed $1200. "
         "Pickup March 10th 9am from 55 Harbor Blvd Miami FL 33101. "
         "Delivering to 300 Commerce Street Atlanta GA 30301. 10 cartons, 200kg electronics."),

        ("Cancel Order ORD-4821",
         "We need to cancel order ORD-4821 booked for March 8th Houston TX to Phoenix AZ. "
         "Project pushed back indefinitely. Please refund $500 deposit. Emily Watson, BuildRight."),

        ("Quick question",
         "Hey, we might need to move some stuff in the coming weeks. "
         "Nothing confirmed yet. Will be in touch. Thanks."),

        ("Shipment inquiry - Boston office furniture",
         "Looking to ship office furniture, 10 pallets from Boston warehouse zip 02101. "
         "Weight 850kg, volume 12 CBM. Sea freight, LCL. Not dangerous, stackable. "
         "Reference REQ-7731. Contact Mark Evans mark@company.com. "
         "Destination not decided yet, incoterm not sorted."),
    ]

    passed = 0
    failed = 0
    expected_intents = [
        "new_request", "status_inquiry", "confirmation",
        "cancellation", "missing_information", "missing_information"
    ]

    for i, ((subject, body), expected) in enumerate(zip(test_emails, expected_intents), 1):
        print(f"\n{'=' * 60}")
        print(f"Test {i}: {subject}")
        print(f"Expected : {expected}")
        try:
            result = detect_intent(subject, body)
            status = "✅ PASS" if result.intent.value == expected else "❌ FAIL"
            print(f"Got      : {result.intent.value}  {status}")
            print(f"Confidence: {result.confidence:.2f}")
            print(f"Reason   : {result.reason}")

            if result.intent == EmailIntent.MISSING_INFORMATION:
                print(f"Request ID: {result.request_id or 'NOT FOUND'}")
                if result.provided_fields:
                    print("Provided  :")
                    for f in result.provided_fields:
                        print(f"  - {f.field}: {f.value}")

                # Simulate what intent_node does with provided_fields
                request_data = {f.field: f.value for f in result.provided_fields if f.value} if result.provided_fields else {}
                missing_fields = [f for f in REQUIRED_FIELDS if f not in request_data]
                print(f"Missing (computed): {missing_fields}")

            if result.intent.value == expected:
                passed += 1
            else:
                failed += 1

        except ValueError as e:
            print(f"[ERROR] {e}")
            failed += 1
        except RuntimeError as e:
            print(f"[ERROR] {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(test_emails)} tests")
