from typing import Optional, Dict, List
from typing_extensions import TypedDict
from models.shipment import (
    Message,
    Attachment,
    PricingSchema,
    LanguageMetadata,
    ValidationResult
    )


class AgentState(TypedDict):
    # ── Email / Identity ──────────────────────────────────
    raw_email: bytes
    request_id:        str
    thread_id:         Optional[str]
    conversation_id:   Optional[str]
    customer_email:    str
    subject:           Optional[str]
    message_ids:       List[str]
    body:              str
    translated_body:   str
    translated_subject: str
    status: str
    intent: Optional[str]
    last_message_id: Optional[str]

    # ── Language ──────────────────────────────────────────
    language_metadata: LanguageMetadata

    # ── Extracted Data ────────────────────────────────────
    request_data:      Dict

    # ── Validation ────────────────────────────────────────
    validation_result: ValidationResult

    # ── Pricing ───────────────────────────────────────────
    pricing_details:   List[PricingSchema]

    # ── Conversation ──────────────────────────────────────
    messages:          List[Message]
    attachments:       List[Attachment]

    # ── Output ────────────────────────────────────────────
    final_document:    Optional[str]
