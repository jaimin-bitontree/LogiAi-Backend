from config.settings import settings
from agent.state import AgentState
from models.shipment import LanguageMetadata
from services.ai.language_service import detect_language, translate_with_llm


def language_node(state: AgentState) -> dict:
    body    = state["body"]
    subject = state["subject"]

    # Step 1: Detect body and subject language independently
    body_lang, body_confidence = detect_language(body) if body else ("en", 1.0)
    subj_lang, _               = detect_language(subject) if subject else ("en", 1.0)

    # Step 2: Translate body if not English
    if body_lang == "en":
        translated_body = body
        body_translated = False
    else:
        translated_body = translate_with_llm(body)
        body_translated = True

    # Step 3: Translate subject if not English
    if subj_lang == "en":
        translated_subject = subject
        subject_translated = False
    else:
        translated_subject = translate_with_llm(subject) if subject else ""
        subject_translated = bool(subject)

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