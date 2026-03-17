import re
import logging
from groq import Groq
from langdetect import detect_langs, LangDetectException
from config.settings import settings
from utils.language_helpers import protect_req_ids, restore_req_ids

logger = logging.getLogger(__name__)
client = Groq(api_key=settings.GROQ_API_KEY)
#genai.configure(api_key=settings.GEMINI_API_KEY)


def detect_language(text: str) -> tuple[str, float]:
    """Detect language using langdetect with LLM fallback."""
    try:
        results    = detect_langs(text)
        top        = results[0]
        lang       = str(top.lang)
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
            #model = genai.GenerativeModel(
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
            #model = genai.GenerativeModel(
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
        return text


def translate_text_to_language(text: str, target_lang: str) -> str:
    """
    Translate plain text (not HTML) to target language.
    Use this for subjects, short messages — NOT for HTML bodies.
    REQ-YYYY-XXXXXXXXXX IDs are preserved and never translated.

    Args:
        text: Plain text to translate
        target_lang: ISO 639-1 language code (e.g. 'fr', 'de', 'hi', 'ar')

    Returns:
        Translated plain text. Returns original if translation fails.
    """
    if not target_lang or target_lang == "en":
        return text

    protected, placeholders = protect_req_ids(text)

    try:
        response = client.chat.completions.create(
            #model = genai.GenerativeModel(
            model=settings.LANGUAGE_TRANSLATE_MODEL,
            max_tokens=300,
            messages=[
                {
                    "role": "system",
                    "content": (
                       f"You are a professional human translator. "
                       f"Your task: translate the user's text into the language identified by ISO 639-1 code '{target_lang}'. "
                       f"\n\nRULES (follow strictly):"
                       f"\n- Output ONLY the translated text — no introductions, explanations, notes, or metadata."
                       f"\n- Preserve the original formatting, line breaks, punctuation, and structure exactly."
                       f"\n- Preserve proper nouns, brand names, URLs, code snippets, and placeholders as-is (e.g. {{name}}, %s, <tag>)."
                       f"\n- Match the tone and register of the source: formal stays formal, casual stays casual."
                       f"\n- Never add, remove, or paraphrase content — translate meaning faithfully."
                       f"\n- If a phrase has no direct equivalent, use the most natural culturally appropriate expression."
                       f"\n- Do not transliterate — write in the native script of the target language."
                       f"\n\nTranslate now."
)
                },
                {"role": "user", "content": protected}
            ],
            temperature=0
        )
        translated = response.choices[0].message.content.strip()
        translated = restore_req_ids(translated, placeholders)
        logger.info(f"[language_service] Text translated to '{target_lang}': {translated}")
        return translated
    except Exception as e:
        logger.error(f"[language_service] Text translation failed: {e}")
        return text


def _split_html_into_chunks(text: str, chunk_size: int = 4000) -> list:
    """
    Split HTML into chunks at safe </div> boundaries.
    Avoids cutting mid-tag which would break HTML structure.
    Falls back to raw split if no safe boundary found.
    """
    parts = re.split(r'(?<=</div>)', text)

    chunks = []
    current = ""
    for part in parts:
        if len(current) + len(part) <= chunk_size:
            current += part
        else:
            if current:
                chunks.append(current)
            if len(part) > chunk_size:
                for i in range(0, len(part), chunk_size):
                    chunks.append(part[i:i + chunk_size])
                current = ""
            else:
                current = part
    if current:
        chunks.append(current)

    return chunks


def _strip_llm_preamble(text: str) -> str:
    """
    Remove any LLM preamble text before the actual HTML.
    e.g. 'Here is the translated HTML:' added by the LLM before <html> or <div>
    """
    first_tag = text.find("<")
    if first_tag > 0:
        logger.warning(f"[language_service] Stripping LLM preamble: {text[:first_tag].strip()}")
        return text[first_tag:]
    return text


def translate_to_language(text: str, target_lang: str) -> str:
    """
    Translate HTML from English to target language.
    Splits HTML at safe </div> boundaries to avoid cutting mid-tag.
    Strips any LLM preamble sentences from each chunk.

    Use this ONLY for HTML bodies — not for plain text.
    For plain text (subjects, short messages), use translate_text_to_language().

    Args:
        text: English HTML to translate
        target_lang: ISO 639-1 language code (e.g. 'fr', 'de', 'hi', 'ar')

    Returns:
        Translated HTML in target language. Returns original if translation fails.
    """
    if not target_lang or target_lang == "en":
        return text

    protected_text, placeholders = protect_req_ids(text)
    chunks = _split_html_into_chunks(protected_text, chunk_size=4000)
    translated_chunks = []

    logger.info(f"[language_service] Translating HTML to '{target_lang}' | {len(text)} chars | {len(chunks)} chunk(s)")

    for i, chunk in enumerate(chunks):
        try:
            response = client.chat.completions.create(
                #model = genai.GenerativeModel(
                model=settings.LANGUAGE_TRANSLATE_MODEL,
                max_tokens=8000,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"You are a professional translator specializing in natural, fluent translations. "
                            f"Translate the given HTML to the language with ISO 639-1 code: '{target_lang}'. "
                            f"Use natural, grammatically correct phrasing — do NOT translate word by word. "
                            f"Write as a native speaker would — use proper grammar, natural sentence structure, and culturally appropriate tone. "
                            f"ONLY translate visible text — do NOT add, remove, or generate any new content. "
                            f"Do NOT invent new sections, tables, rows, or data that do not exist in the input. "
                            f"Do NOT change numeric values, dates, IDs, email addresses, or Request IDs. "
                            f"Do NOT change numeric values, dates, email addresses, or any token that looks like __REQID0__, __REQID1__, etc. "
                            f"Preserve ALL HTML tags, attributes, and structure exactly as-is. "
                            f"Do NOT modify, remove, or alter any CSS style attributes — preserve padding, margin, color, font-weight, width, border, and all other style values exactly as-is. "
                            f"Only translate the visible human-readable text inside HTML tags. "
                            f"Do NOT add any explanation, preamble, or commentary before or after the HTML. "
                            f"Return ONLY the translated HTML, nothing else."
                        )
                    },
                    {"role": "user", "content": chunk}
                ],
                temperature=0
            )
            translated_chunk = response.choices[0].message.content.strip()
            translated_chunk = _strip_llm_preamble(translated_chunk)

            if not translated_chunk.strip():
                logger.warning(f"[language_service] Chunk {i + 1}/{len(chunks)} returned empty — using original chunk")
                translated_chunks.append(chunk)
            else:
                translated_chunks.append(translated_chunk)
            logger.info(f"[language_service] Chunk {i + 1}/{len(chunks)} done ({len(chunk)} → {len(translated_chunk)} chars)")
        except Exception as e:
            logger.error(f"[language_service] Chunk {i + 1}/{len(chunks)} failed: {e} — using original chunk")
            translated_chunks.append(chunk)
            continue

        if not translated_chunk.strip():
            logger.warning(f"[language_service] Chunk {i + 1}/{len(chunks)} returned empty — using original chunk")
            translated_chunks[-1] = chunk

    translated = "".join(translated_chunks)
    translated = restore_req_ids(translated, placeholders)
    logger.info(f"[language_service] HTML translation complete → '{target_lang}' ({len(translated)} chars)")
    return translated