import json
from groq import Groq
from config import settings
from core.constants import EmailIntent
from models.shipment import IntentResult

client = Groq(api_key=settings.GROQ_API_KEY)

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

1. operator_pricing - Email contains pricing/quotation details from the logistics operator.
                      Look for: prices, rates, costs, freight charges, quotations, USD/EUR amounts.
2. new_request - Sender wants a new shipment AND provides BOTH a clear origin
                AND a clear destination. Both must be present for new_request.
3. status_inquiry - Sender is asking about the status of an existing shipment/order.
4. confirmation - Sender is confirming a previously discussed shipment or booking.
5. cancellation - Sender wants to cancel an existing shipment or order.
6. missing_information - Email is missing origin OR destination OR both, even if other
                         details like weight or volume are present. Also use this if the
                         email is too vague to process as a shipment request.

Also extract "request_id" — any shipment ID, order ID, tracking number, booking
reference, or customer reference found anywhere in the email. If none, set null.

Respond ONLY in this exact JSON format, no extra text, no markdown:
{
  "intent": "<operator_pricing | new_request | status_inquiry | confirmation | cancellation | missing_information>",
  "request_id": "<extracted ID or null>"
}
""".strip()


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
            model=settings.LANGUAGE_DETECT_MODEL,   # uses llama-3.1-8b-instant from config
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
        print(f"[intent_service] detect_intent() | subject: '{subject[:50]}' | body: '{body[:50]}...'")
