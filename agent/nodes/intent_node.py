import json
import os
from enum import Enum
from typing import Optional

from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel

from agent.state import AgentState

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


class IntentResult(BaseModel):
    intent: EmailIntent
    request_id: Optional[str] = None


# ===================================================
# SYSTEM PROMPT
# ===================================================

INTENT_SYSTEM_PROMPT = """
You are an email intent classifier for a logistics platform called LogiAI.

You will receive an email with a Subject line and a Body.
Both the subject and body together form the full context read BOTH carefully.
The subject alone may reveal the intent even if the body is short or vague.
Emails may be written as plain conversational paragraphs with no labels or structure.

Classify the given email into exactly ONE of these intents:

1. new_request - Sender wants a new shipment AND provides BOTH a clear origin
                AND a clear destination. Both must be present for new_request.
2. status_inquiry - Sender is asking about the status of an existing shipment/order.
3. confirmation - Sender is confirming a previously discussed shipment or booking.
4. cancellation - Sender wants to cancel an existing shipment or order.
5. missing_information - Email is missing origin OR destination OR both, even if other
                         details like weight or volume are present. Also use this if the
                         email is too vague to process as a shipment request.

Also extract "request_id" — any shipment ID, order ID, tracking number, booking
reference, or customer reference found anywhere in the email. If none, set null.

Respond ONLY in this exact JSON format, no extra text, no markdown:
{
  "intent": "<new_request | status_inquiry | confirmation | cancellation | missing_information>",
  "request_id": "<extracted ID or null>"
}
""".strip()


# ===================================================
# CORE FUNCTION
# ===================================================

def detect_intent(email_subject: str, email_body: str) -> IntentResult:
    """
    Classifies intent and extracts request_id from a logistics email.
    Reads translated_subject and translated_body (always English).
    """
    subject = (email_subject or "").strip()
    body = (email_body or "").strip()

    if not subject and not body:
        return IntentResult(
            intent=EmailIntent.MISSING_INFORMATION,
            request_id=None,
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
            max_tokens=64,   
        )

        raw_text = response.choices[0].message.content.strip()
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

        parsed = json.loads(raw_text)

        return IntentResult(
            intent=EmailIntent(parsed["intent"]),
            request_id=parsed.get("request_id"),
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
    """
    Reads translated_subject and translated_body from state.
    Returns only intent and request_id (if found).
    """
    result = detect_intent(
        state.get("translated_subject", ""),
        state.get("translated_body", ""),
    )

    _print_intent_result(state.get("translated_subject", ""), result)

    output = {"intent": result.intent.value}
    if result.request_id:
        output["request_id"] = result.request_id

    return {
        "intent": result.intent.value,
        "request_id": result.request_id or "",
    }


# ===================================================
# CONSOLE PRINT HELPER
# ===================================================

def _print_intent_result(subject: str, result: IntentResult) -> None:
    print("\n" + "=" * 60)
    print("[intent_node] RESULT")
    print(f"  Subject    : {subject.strip() or '(no subject)'}")
    print(f"  Intent     : {result.intent.value}")
    print(f"  Request ID : {result.request_id or 'NOT FOUND'}")
    print("=" * 60)
