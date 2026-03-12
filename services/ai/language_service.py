import logging
from groq import Groq
from langdetect import detect_langs, LangDetectException
from config.settings import settings

logger = logging.getLogger(__name__)
client = Groq(api_key=settings.GROQ_API_KEY)


def detect_language(text: str) -> tuple[str, float]:
    """Detect language using langdetect with LLM fallback."""
    try:
        results = detect_langs(text)
        top = results[0]
        lang = str(top.lang)
        confidence = float(top.prob)
    except LangDetectException:
        return "en", 0.0
    except Exception as e:
        logger.error(f"langdetect error: {e}")
        return "en", 0.0

    if confidence < settings.LANGUAGE_CONFIDENCE_THRESHOLD:
        lang, confidence = detect_language_with_llm(text)

    return lang, confidence


def detect_language_with_llm(text: str) -> tuple[str, float]:
    try:
        response = client.chat.completions.create(
            model=settings.LANGUAGE_DETECT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a language detection expert. "
                        "Respond with only the ISO 639-1 language code (e.g. 'en', 'fr', 'de', 'hi'). "
                        "Nothing else."
                    )
                },
                {"role": "user", "content": f"Detect the language:\n\n{text[:500]}"}
            ],
            temperature=0
        )
        lang = response.choices[0].message.content.strip().lower()
        return lang, 1.0
    except Exception as e:
        logger.error(f"LLM language detection failed: {e}")
        return "en", 0.0


def translate_with_llm(text: str) -> str:
    try:
        response = client.chat.completions.create(
            model=settings.LANGUAGE_TRANSLATE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional translator. "
                        "Translate the given text to English. "
                        "Return only the translated text, nothing else."
                    )
                },
                {"role": "user", "content": text[:4000]}
            ],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM translation failed: {e}")
        return text   # return original if translation fails


def translate_to_language(text: str, target_lang: str) -> str:
    """
    Translate text from English to target language.
    Used to translate reply emails back to customer's language.

    Args:
        text: English text to translate (can be HTML)
        target_lang: ISO 639-1 language code (e.g. 'fr', 'de', 'hi', 'ar')

    Returns:
        Translated text in target language. Returns original if translation fails.
    """
    if not target_lang or target_lang == "en":
        return text
    try:
        response = client.chat.completions.create(
            model=settings.LANGUAGE_TRANSLATE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional translator. "
                        f"Translate the given text to the language with ISO 639-1 code: '{target_lang}'. "
                        f"Preserve all HTML tags, formatting, and structure exactly. "
                        f"Only translate the visible text content inside HTML tags. "
                        f"Do NOT translate HTML tag names, attributes, or CSS. "
                        f"Return only the translated result, nothing else."
                    )
                },
                {"role": "user", "content": text[:4000]}
            ],
            temperature=0
        )
        translated = response.choices[0].message.content.strip()
        logger.info(f"[language_service] Translated reply to '{target_lang}' ({len(translated)} chars)")
        return translated
    except Exception as e:
        logger.error(f"[language_service] Translation to '{target_lang}' failed: {e} — using original")
        return text  # return original if translation fails
