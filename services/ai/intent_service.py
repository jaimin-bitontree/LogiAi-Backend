import json
import logging
from groq import Groq
from config.settings import settings
from config.constants import EmailIntent
from models.shipment import IntentResult

logger = logging.getLogger(__name__)
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

1. operator_pricing - Email FROM the logistics operator TO the customer containing actual pricing/quotation details.
                      Look for: specific prices, rates, costs, freight charges, quotations with USD/EUR amounts.
                      MUST contain actual numerical pricing data, not just requests for pricing.
                      Examples: "Your quotation is $2,500", "Freight rate: EUR 1,800", "Total cost: $3,200"
                      IMPORTANT: Must have actual dollar amounts or detailed pricing breakdown

2. new_request - Customer is REQUESTING a new shipment quotation AND provides BOTH a clear origin
                AND a clear destination. Both must be present for new_request.
                Keywords: "request quotation", "need quote", "please provide pricing", "shipment request"
                Examples: "I would like to request a quotation", "Please provide pricing for shipment"
                IMPORTANT: If someone is ASKING for pricing, it's new_request, NOT operator_pricing

3. status_inquiry - Sender is asking about the status of an existing shipment/order.
                   Keywords: "status", "update", "where is my shipment", "tracking"

4. confirmation - Sender is confirming a previously discussed shipment or booking.
                 Keywords: "confirm", "accept", "proceed", "book", "yes please go ahead", "accepted", "approve"
                 Examples: "REQ-123 accepted", "I accept the quote", "Please proceed with booking"

5. cancellation - Sender wants to cancel an existing shipment or order.
                 Keywords: "cancel", "stop", "abort", "withdraw"

6. missing_information - Email is missing origin OR destination OR both, even if other
                         details like weight or volume are present. Also use this if the
                         email is too vague to process as a shipment request.

7. spam - Email is clearly spam, phishing, marketing, or not related to logistics.
          Look for: promotional content, phishing attempts, unrelated topics,
          suspicious links, requests for personal info, "click here", "verify account"
          Examples: "Congratulations you won!", "Verify your PayPal", "Buy cheap products"
          CRITICAL: Only mark as spam if VERY CLEAR. When in doubt, use missing_information.

CRITICAL DISTINCTION - READ CAREFULLY:
- If email is REQUESTING pricing/quotation (customer asking) → new_request
- If email is PROVIDING actual pricing/quotation (operator answering with numbers) → operator_pricing
- Words like "request quotation", "need quote", "please provide" = new_request
- Only use operator_pricing if you see actual dollar amounts, rates, or prices being PROVIDED

Also extract "request_id" — any shipment ID, order ID, tracking number, booking
reference, or customer reference found anywhere in the email. If none, set null.

Respond ONLY in this exact JSON format, no extra text, no markdown:
{
  "intent": "<operator_pricing | new_request | status_inquiry | confirmation | cancellation | missing_information | spam>",
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
        logger.debug(f"[intent_service] detect_intent() | subject: '{subject[:50]}' | body: '{body[:50]}...'")
