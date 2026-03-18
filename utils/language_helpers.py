"""
utils/language_helpers.py

Shared language utility helpers used across tools and nodes.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Minimum body length to trust langdetect alone.
# Short replies (e.g. "Modo de transporte: Marítimo") are often misclassified.
MIN_BODY_LEN_FOR_DETECTION = 80

_REQ_ID_PATTERN = re.compile(r'REQ-\d{4}-\d+')


def get_detected_lang(shipment_doc: dict) -> str:
    """Extract detected_language from a shipment document fetched from DB."""
    if not shipment_doc:
        return "en"
    lang_meta = shipment_doc.get("language_metadata", {})
    if isinstance(lang_meta, dict):
        detected = lang_meta.get("detected_language") or "en"
    else:
        detected = getattr(lang_meta, "detected_language", None) or "en"
    logger.debug(f"[language_helpers] get_detected_lang={detected}")
    return detected


def protect_req_ids(text: str) -> tuple[str, dict]:
    """Replace REQ-YYYY-XXXXXXXXXX patterns with placeholders before translation."""
    placeholders = {}

    def replacer(m):
        key = f"__REQID{len(placeholders)}__"
        placeholders[key] = m.group(0)
        return key

    protected = _REQ_ID_PATTERN.sub(replacer, text)
    return protected, placeholders


def restore_req_ids(text: str, placeholders: dict) -> str:
    """Restore original REQ IDs from placeholders after translation."""
    for key, original in placeholders.items():
        text = text.replace(key, original)
    return text
