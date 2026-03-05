import json
import os
from dotenv import load_dotenv
load_dotenv()
from typing import Optional
from enum import Enum
from groq import Groq
from pydantic import BaseModel
from core.constants import REQUIRED_FIELDS, OPTIONAL_FIELDS
from agent.state import AgentState

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
    intent:          EmailIntent
    confidence:      float
    reason:          str
    request_id:      Optional[str] = None
    provided_fields: Optional[list[FieldDetail]] = None
    missing_fields:  Optional[list[str]] = None


# ===================================================
# SYSTEM PROMPT
# ===================================================

INTENT_SYSTEM_PROMPT = f"""
You are an email intent classifier for a logistics platform called LogiAI.

You will receive an email with a Subject line and a Body.
Both the subject and body together form the full context — read BOTH carefully.
The subject alone may reveal the intent even if the body is short or vague.
Emails may be written as plain conversational paragraphs with no labels or structure.

Classify the given email body into exactly ONE of these intents:

1. new_request         - Sender wants a new shipment, pickup, or logistics service.
2. status_inquiry      - Sender is asking about the status of an existing shipment/order.
3. confirmation        - Sender is confirming a previously discussed shipment or booking.
4. cancellation        - Sender wants to cancel an existing shipment or order.
5. missing_information - Email is too vague or missing critical required logistics fields.
                         If the email has NO origin, NO destination, NO quantity, and NO
                         item details — it MUST be missing_information even if it hints
                         at a future shipment or asks about options.

The logistics schema has these REQUIRED fields:
{json.dumps(REQUIRED_FIELDS, indent=2)}

And these OPTIONAL fields:
{json.dumps(OPTIONAL_FIELDS, indent=2)}

ONLY when intent is missing_information, you MUST:
1. Extract "request_id" from the email — any shipment ID, order ID, tracking number,
   booking ref, or customer reference found anywhere in the text. If none, set null.
2. Go through EVERY field (required + optional) and scan the paragraph carefully:
   - Value IS mentioned anywhere in text -> add to "provided_fields":
     {{"field": "<field_name>", "value": "<extracted value>"}}
   - Value is NOT mentioned -> add field name to "missing_fields"

Respond ONLY in this exact JSON format, no extra text, no markdown:
{{
  "intent": "<new_request | status_inquiry | confirmation | cancellation | missing_information>",
  "confidence": <float 0.0 to 1.0>,
  "reason": "<one sentence explanation>",
  "request_id": "<extracted ID or null>",
  "provided_fields": [{{"field": "field_name", "value": "extracted value"}}],
  "missing_fields": ["field1", "field2"]
}}

Note: "request_id", "provided_fields", and "missing_fields" are ONLY populated
when intent is missing_information. For all other intents set all three to null.
""".strip()


# ===================================================
# MAIN FUNCTION
# ===================================================

def detect_intent(email_subject: str, email_body: str) -> IntentResult:
    """
    Detects the intent of a logistics email using Groq LLM.
    Expects TRANSLATED subject and body (always English).
    Called by intent_node() which reads translated_subject and
    translated_body from AgentState.

    Returns IntentResult with:
      - intent          : one of the 5 EmailIntent values
      - confidence      : float 0.0 to 1.0
      - reason          : one sentence explanation from LLM
      - request_id      : only for missing_information — any ref ID found
      - provided_fields : only for missing_information — fields found in email
      - missing_fields  : only for missing_information — fields not found
    """

    subject = (email_subject or "").strip()
    body = (email_body or "").strip()

    # Guard clause — both subject and body are empty
    if not subject and not body:
        return IntentResult(
            intent=EmailIntent.MISSING_INFORMATION,
            confidence=1.0,
            reason="Email subject and body are both empty.",
            request_id=None,
            provided_fields=None,
            missing_fields=REQUIRED_FIELDS,
        )

    # Build the combined input sent to the LLM
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

        # FIX 5: Strip markdown code fences if LLM wraps response in ```json
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

        parsed = json.loads(raw_text)

        # Build provided_fields list only if present (missing_information intent)
        provided = None
        if parsed.get("provided_fields"):
            provided = [
                FieldDetail(field=f["field"], value=f.get("value"))
                for f in parsed["provided_fields"]
            ]

        return IntentResult(
            intent=EmailIntent(parsed["intent"]),
            confidence=float(parsed["confidence"]),
            reason=parsed["reason"],
            request_id=parsed.get("request_id"),
            provided_fields=provided,
            missing_fields=parsed.get("missing_fields"),
        )

    except json.JSONDecodeError as e:
        # LLM returned text that is not valid JSON
        raise ValueError(f"LLM returned invalid JSON: {e}")

    except KeyError as e:
        # JSON parsed but a required key like 'intent' or 'confidence' is missing
        raise ValueError(f"Missing expected field in LLM response: {e}")

    except ValueError as e:
        # Intent string returned by LLM does not match any EmailIntent enum value
        raise ValueError(f"Invalid intent value returned by LLM: {e}")

    except Exception as e:
        # Groq API down, network timeout, rate limit, or any unexpected error
        raise RuntimeError(f"Intent detection failed: {e}")

    finally:
        # Always logs — whether success or error
        print(f"[intent_node] detect_intent() called | subject: '{subject[:50]}' | body: '{body[:50]}...'")


# ===================================================
# LANGGRAPH NODE
# ===================================================

def intent_node(state: AgentState) -> dict:
    """
    LangGraph node that reads translated_subject and translated_body
    from state, runs detect_intent, and writes intent back to state.
    Also prints a clear console summary for every email processed.
    """
    translated_subject = state.get("translated_subject", "")
    translated_body = state.get("translated_body", "")

    result = detect_intent(translated_subject, translated_body)

    # Print result to console
    _print_intent_result(translated_subject, result)

    # Return only the fields this node changes — LangGraph merges it into state
    return {
        "intent": result.intent.value,
    }


def _print_intent_result(subject: str, result: IntentResult) -> None:
    """Prints a clean intent detection summary to the console."""
    print("\n" + "=" * 60)
    print(f"[intent_node] RESULT")
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
# MANUAL TEST — run with: python intent_node.py
# ===================================================

if __name__ == "__main__":

    test_emails = [
        # (subject, body)

        # new_request
        (
            "Shipment Request - Chicago to Dallas",
            """
            Hi, we are SteelCore Manufacturing based out of Chicago and we need to move
            some industrial conveyor belt parts to our client down in Dallas Texas. We have
            got 3 pallets ready to go, each one is about 500 kg so 1500 kg in total and each
            pallet is roughly 120 by 80 by 100 centimeters. Our warehouse is at 142 West
            Industrial Ave Chicago IL 60601 and the delivery should go to 300 Commerce Street
            Dallas TX 75201. We are thinking sea freight, FCL, EXW incoterm. We would need
            pickup by March 14th somewhere between 9 and 12 in the morning. You can reach
            John Miller on +1-312-555-0192 if you need anything. Let us know pricing and
            available slots please.
            """
        ),

        # status_inquiry — subject carries the intent clearly
        (
            "Follow up on SHP-20948",
            """
            Hey there, I am following up on a shipment we sent out from Miami to Atlanta
            back on February 20th. It was supposed to land by March 1st but we still have
            not received anything. Our client is really pushing us for an update so if
            someone could check where the goods are and give us a realistic ETA that would
            be great. Sarah Thompson here from the supply chain team.
            """
        ),

        # confirmation
        (
            "Booking Confirmation BK-3821",
            """
            Hi just writing to confirm everything we talked about on the call with Kevin on
            March 3rd. Invoice INV-992, we agreed on twelve hundred dollars and we will
            process the payment today. Pickup is set for March 10th at 9 in the morning from
            Warehouse A at 55 Harbor Blvd Miami FL 33101 and it goes to 300 Commerce Street
            Atlanta GA 30301. We are sending 10 cartons of consumer electronics weighing
            200 kg in total. Please send the final invoice to billing@clientb.com. Thanks,
            David Chen.
            """
        ),

        # cancellation — subject makes it unambiguous
        (
            "Cancel Order ORD-4821",
            """
            Hello, our client has pushed the whole project back indefinitely so we simply
            do not need the shipment anymore. We paid a five hundred dollar deposit on
            March 1st and would like that refunded. Could you please confirm in writing
            that the order is cancelled? Thanks, Emily Watson from BuildRight.
            """
        ),

        # missing_information — vague body, vague subject
        (
            "Quick question",
            """
            Hey just wanted to shoot a quick message and say we might be needing to move
            some stuff in the coming weeks. Nothing is confirmed on our side just yet.
            Will be in touch once things are a bit clearer. Thanks.
            """
        ),

        # missing_information — partial fields, subject gives extra context
        (
            "Shipment inquiry - Boston office furniture",
            """
            Hi there, we are looking to arrange a shipment of office furniture, around
            10 pallets worth, coming out of our Boston warehouse which is in zip code 02101.
            Total weight is about 850 kg and volume is roughly 12 CBM. We are thinking sea
            freight and LCL. The goods are not dangerous and they are stackable. Our internal
            reference for this is REQ-7731 and you can contact Mark Evans at mark@company.com.
            We have not nailed down the destination yet and we also do not have the incoterm
            sorted out yet. Let us know how to proceed.
            """
        ),
    ]

    for i, (subject, body) in enumerate(test_emails, 1):
        print(f"\n{'=' * 60}")
        print(f"Test {i}:")
        print(f"Subject: {subject.strip()}")
        try:
            result = detect_intent(subject, body)
            print(f"Intent    : {result.intent.value}")
            print(f"Confidence: {result.confidence:.2f}")
            print(f"Reason    : {result.reason}")

            if result.intent == EmailIntent.MISSING_INFORMATION:
                print(f"Request ID: {result.request_id or 'NOT FOUND'}")
                if result.provided_fields:
                    print("Provided  :")
                    for f in result.provided_fields:
                        print(f"  - {f.field}: {f.value}")

        except ValueError as e:
            print(f"[ERROR] Bad LLM response: {e}")
        except RuntimeError as e:
            print(f"[ERROR] Service error: {e}")
