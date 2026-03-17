import json
import logging
from groq import Groq
from config.settings import settings
from config.constants import EmailIntent
from models.shipment import IntentResult

logger = logging.getLogger(__name__)
client = Groq(api_key=settings.GROQ_API_KEY_2)

# ===================================================
# SYSTEM PROMPT
# ===================================================

INTENT_SYSTEM_PROMPT = """
You are an email intent classifier for a logistics platform called LogiAI.

You will receive an email with a Subject line and a Body.
Both the subject and body together form the full context — read BOTH carefully.
The subject alone may reveal the intent even if the body is short or vague.
Emails may be written as plain conversational paragraphs with no labels or structure.

The body may also contain text extracted from PDF attachments marked as [PDF: filename].
READ the PDF content carefully — it is part of the email context and may contain all shipment details.

Classify the given email into exactly ONE of these intents:

1. operator_pricing - Email FROM the logistics operator TO the customer containing actual pricing/quotation details.
                      Look for: specific prices, rates, costs, freight charges, quotations with USD/EUR amounts.
                      MUST contain actual numerical pricing data, not just requests for pricing.
                      Examples: "Your quotation is $2,500", "Freight rate: EUR 1,800", "Total cost: $3,200"
                      IMPORTANT: Must have actual dollar amounts or detailed pricing breakdown

2. new_request - Customer is sending a shipment request that includes BOTH a clear origin AND a clear destination.
                Both must be present somewhere in the email OR in the attached PDF content.
                Keywords: "request quotation", "need quote", "please provide pricing", "shipment request"
                Examples: "I would like to request a quotation", "Please provide pricing for shipment"
                IMPORTANT: If the PDF attachment contains origin and destination → classify as new_request
                IMPORTANT: If someone is ASKING for pricing, it's new_request, NOT operator_pricing
                IMPORTANT: Even if the email body text is vague or short (e.g. "please refer attachments"),
                           if the PDF content has origin + destination → it is new_request

3. status_inquiry - Sender is asking about the status of an existing shipment/order.
                   Keywords: "status", "update", "where is my shipment", "tracking", "what is the status",
                   "can you check", "shipment status", "order status", "current status", "progress",
                   "delivery status", "check status", "any updates", "when will it arrive"
                   Examples: "What is the status of my shipment?", "Can you check the status?",
                   "Where is my order?", "Any updates on my shipment?", "When will it be delivered?"
                   IMPORTANT: If email asks about status of an existing shipment → classify as status_inquiry
                   IMPORTANT: Status inquiry does NOT need to include request_id in the email itself
                   
                   EXCEPTION: If subject contains "Status Update" BUT body contains shipment data
                   (volume, weight, container type, dimensions, cargo details), then classify as
                   missing_information instead - customer is providing data, not asking for status.

4. confirmation - Sender is confirming a previously discussed shipment or booking.
                 Keywords: "confirm", "accept", "proceed", "book", "yes please go ahead", "accepted", "approve"
                 Examples: "REQ-123 accepted", "I accept the quote", "Please proceed with booking"

5. cancellation - Sender wants to cancel an existing shipment or order.
                 Keywords: "cancel", "stop", "abort", "withdraw"

6. missing_information - Email is missing origin OR destination OR both, even if other
                         details like weight or volume are present. Also use this if the
                         email is too vague to process as a shipment request.
                         IMPORTANT: Only use this if email shows INTENT to ship but lacks details.

7. spam - Email is clearly spam, phishing, marketing, irrelevant, or off-topic.
          
          SPAM INDICATORS (Malicious/Marketing):
          - Phishing attempts: "verify account", "confirm password", "update payment"
          - Marketing: "buy now", "limited offer", "click here", "special discount"
          - Promotional: "congratulations you won", "claim prize", "free money"
          - Suspicious links: "bit.ly", "tinyurl", shortened URLs
          - Requests for personal info: "send credit card", "bank details", "SSN"
          - Lottery/Prize scams: "you won", "congratulations", "claim reward"
          
          IRRELEVANT/OFF-TOPIC INDICATORS (Not malicious, just not logistics):
          - Casual greetings ONLY: "hello how are you", "hi there", "what's up"
          - Personal chat: "just checking in", "how's the weather", "nice to meet you"
          - No shipment keywords at all: no mention of cargo, origin, destination, weight, etc.
          - Very short emails (< 20 words) with no logistics content
          - Completely unrelated topics: "can you help with my homework", "fix my computer"
          - Social emails: "let's grab coffee", "see you soon", "happy birthday"
          
          CRITICAL RULES FOR SPAM CLASSIFICATION:
          1. If email mentions ANY shipment-related keywords (origin, destination, weight, cargo, 
             container, port, freight, shipping, delivery, quote, pricing) → NOT spam
          2. If email is asking for shipment details (even vaguely) → NOT spam, use missing_information
          3. Only mark as spam if VERY CLEAR it's either:
             - Malicious/phishing/marketing, OR
             - Completely off-topic with NO logistics intent whatsoever
          4. When in doubt between spam and missing_information → use missing_information
          
          Examples of SPAM:
          - "Congratulations you won $1,000,000!"
          - "Hello how are you doing?" (no logistics context)
          - "Verify your PayPal account"
          - "Click here for free shipping" (marketing)
          - "Just saying hi, how's life?" (pure social, no logistics)
          
          Examples of NOT SPAM (use missing_information instead):
          - "I need to ship something but don't have details yet"
          - "Can you help me with a shipment?" (vague but shows intent)
          - "What's the process for shipping?" (asking about logistics)

CRITICAL DISTINCTION - READ CAREFULLY:
- If email is REQUESTING pricing/quotation (customer asking) → new_request
- If email is PROVIDING actual pricing/quotation (operator answering with numbers) → operator_pricing
- Words like "request quotation", "need quote", "please provide" = new_request
- Only use operator_pricing if you see actual dollar amounts, rates, or prices being PROVIDED
- PDF content counts as part of the email — if PDF has origin + destination → new_request

Also extract "request_id" — ONLY extract IDs that follow this exact format: REQ-YYYY-XXXXXXXXXX
Example: REQ-2026-0311081356708170
Any other document numbers like PKL-, INV-, DOC-, SC- are NOT request IDs → set null.
If no REQ- format ID found → set null.

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
        logger.debug(f"[intent_service] detect_intent() | subject: '{subject[:50]}' | body: '{body[:50]}...'")