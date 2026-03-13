from typing import Optional, Dict, List, Annotated
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from models.shipment import (
    Attachment,
    PricingSchema,
    LanguageMetadata,
    ValidationResult
    )


class AgentState(TypedDict):
    # ── Email / Identity ──────────────────────────────────
    raw_email: bytes
    request_id:        str
    thread_id:         Optional[str]  # Conversation root (FIRST message)
    conversation_id:   Optional[str]
    customer_email:    str
    subject:           Optional[str]
    message_ids:       List[str]
    body:              str
    translated_body:   str
    translated_subject: str
    status: str
    intent: Optional[str]
    last_message_id: Optional[str]  # Current head (LATEST message)
    shipment_found: bool = False  # Flag for routing (set by parse_node)
    is_operator: bool = False
    email_tool_executed: bool = False  # Flag to prevent duplicate email sending

    # ── Language ──────────────────────────────────────────
    language_metadata: LanguageMetadata

    # ── Extracted Data ────────────────────────────────────
    request_data:      Dict

    # ── Validation ────────────────────────────────────────
    validation_result: ValidationResult

    # ── Pricing ───────────────────────────────────────────
    pricing_details:   List[PricingSchema]

    # ── LangChain agent message history ───────────────────
    # add_messages reducer: new messages are appended, not overwritten
    messages: Annotated[List[BaseMessage], add_messages]

    attachments:       List[Attachment]

    # ── Output ────────────────────────────────────────────
    final_document:    Optional[str]
