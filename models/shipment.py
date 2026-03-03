from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Literal
from datetime import datetime

class Message(BaseModel):
    message_id: str
    sender_email: str
    sender_type: Literal["customer", "operator", "system"]
    direction: Literal["incoming", "outgoing"]
    subject: Optional[str] = None
    body: str
    attachments: Dict = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=datetime.utcnow)


class PricingSchema(BaseModel):
    amount: float
    currency: str
    valid_until: Optional[str] = None
    remarks: Optional[str] = None

# ============================================================
# LANGUAGE METADATA MODEL
# ============================================================

class LanguageMetadata(BaseModel):
    detected_language: Optional[str] = None
    confidence: Optional[float] = None
    translated_to_english: bool = False
    original_text: Optional[str] = None

# ============================================================
# VALIDATION RESULT MODEL
# ============================================================

class ValidationResult(BaseModel):
    is_valid: bool = False
    missing_fields: List[str] = Field(default_factory=list)


class Shipment(BaseModel):
    request_id:        str
    thread_id           :   Optional[str] = None
    customer_email:    str
    subject:           Optional[str] = None

    status:            str  = "NEW"
    intent:            Optional[str] = None

    language_metadata: LanguageMetadata  = Field(default_factory=LanguageMetadata)
    request_data:      Dict              = {}
    validation_result: ValidationResult  = Field(default_factory=ValidationResult)
    pricing_details:   List[PricingSchema]       = []
    attachments:       Dict       = {}

    messages:          List[Message] = []
    message_ids:       List[str]  = []

    final_document:    Optional[str] = None

    created_at:        datetime = Field(default_factory=datetime.utcnow)
    updated_at:        datetime = Field(default_factory=datetime.utcnow)