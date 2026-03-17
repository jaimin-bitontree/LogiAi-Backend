import logging
from agent.state import AgentState
from models.shipment import LanguageMetadata
from services.ai.language_service import detect_language, translate_with_llm
from utils.language_helpers import MIN_BODY_LEN_FOR_DETECTION

logger = logging.getLogger(__name__)


def language_node(state: AgentState) -> dict:
    body            = state["body"]
    subject         = state["subject"]
    conversation_id = state.get("conversation_id")  # set if this is a reply

    # Use only first 1000 chars for detection — avoids English thread pollution
    body_sample = body[:1000] if body else ""

    # Step 1: Detect subject language (subject carries the original thread language)
    subj_lang, subj_confidence = detect_language(subject) if subject else ("en", 1.0)

    # Step 2: Detect body language
    # For short reply bodies, langdetect is unreliable (e.g. "Marítimo" → pt instead of es).
    # Strategy:
    #   - If body is long enough → trust body detection
    #   - If body is short AND it's a reply (conversation_id set) → trust subject language
    #   - If body is short AND it's a new email → use LLM fallback via detect_language
    if body_sample and len(body_sample) >= MIN_BODY_LEN_FOR_DETECTION:
        body_lang, body_confidence = detect_language(body_sample)
    elif body_sample and conversation_id:
        # Short reply — trust the subject language (which carries the original thread lang)
        body_lang, body_confidence = subj_lang, subj_confidence
        logger.info(
            f"[language_node] Short reply body ({len(body_sample)} chars) — "
            f"using subject language '{subj_lang}' instead of re-detecting"
        )
    elif body_sample:
        # Short new email — still try detection (LLM fallback is inside detect_language)
        body_lang, body_confidence = detect_language(body_sample)
    else:
        body_lang, body_confidence = "en", 1.0

    logger.info(f"[language_node] detected={body_lang} | confidence={body_confidence:.4f} | body[:100]={body_sample[:100]!r}")
    logger.info(f"[language_node] subject_lang={subj_lang} | subject={subject!r}")

    # Step 3: Translate body if not English
    if body_lang == "en":
        translated_body = body
        body_translated = False
    else:
        translated_body = translate_text_to_language(body,"en")
        body_translated = True

    # Step 4: Translate subject if not English
    if subj_lang == "en":
        translated_subject = subject
        subject_translated = False
    else:
        translated_subject = translate_text_to_language(subject,"en") if subject else ""
        subject_translated = bool(subject)

    logger.info(f"[language_node] Final → detected_language={body_lang} | body_translated={body_translated}")

    return {
        "language_metadata": LanguageMetadata(
            detected_language=body_lang,
            confidence=body_confidence,
            translated_to_english=body_translated,
            subject_translated_to_english=subject_translated
        ),
        "translated_body":    translated_body,
        "translated_subject": translated_subject
    }