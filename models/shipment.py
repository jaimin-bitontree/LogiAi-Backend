from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Literal
from datetime import datetime
from config.constants import EmailIntent


class IntentResult(BaseModel):
    intent: EmailIntent
    request_id: Optional[str] = None


# ============================================================
# ATTACHMENT MODEL
# ============================================================


class Attachment(BaseModel):
    filename:     str
    content_type: str
    url:          Optional[str]   = None
    public_id:    Optional[str]   = None
    is_relevant:  Optional[bool]  = None  # None=pending, True=uploaded, False=skipped

class Message(BaseModel):
    message_id: str
    sender_email: str
    sender_type: Literal["customer", "operator", "system"]
    direction: Literal["incoming", "outgoing"]
    subject: Optional[str] = None
    body: str
    attachments: List[Attachment] = Field(default_factory=list)
    received_at: datetime = Field(default_factory=datetime.utcnow)


class ChargeItem(BaseModel):
    description: str
    rate: Optional[str] = None
    basis: Optional[str] = None
    amount: str
    currency: str

class ShipmentPricingDetails(BaseModel):
    pol: Optional[str] = None
    pod: Optional[str] = None
    cargo_type: Optional[str] = None
    container_type: Optional[str] = None
    weight_dimensions: Optional[str] = None
    incoterm: Optional[str] = None
    special_requirements: Optional[str] = None
    chargeable_weight: Optional[str] = None
    volume: Optional[str] = None

class PaymentTerms(BaseModel):
    validity: Optional[str] = None
    conditions: Optional[str] = None
    payment_method: Optional[str] = None

class PricingSchema(BaseModel):
    subject: Optional[str] = None
    greeting: Optional[str] = None
    transport_mode: Optional[str] = None
    pricing_type: Optional[str] = None
    shipment_details: ShipmentPricingDetails = Field(default_factory=ShipmentPricingDetails)
    main_freight_charges: List[ChargeItem] = Field(default_factory=list)
    origin_charges: List[ChargeItem] = Field(default_factory=list)
    destination_charges: List[ChargeItem] = Field(default_factory=list)
    additional_charges: List[ChargeItem] = Field(default_factory=list)
    payment_terms: PaymentTerms = Field(default_factory=PaymentTerms)
    calculation_notes: Optional[str] = None
    closing: Optional[str] = None

# ============================================================
# LANGUAGE METADATA MODEL
# ============================================================


class LanguageMetadata(BaseModel):
    detected_language: Optional[str] = None
    confidence: Optional[float] = None
    translated_to_english: bool = False
    subject_translated_to_english: bool = False

# ============================================================
# VALIDATION RESULT MODEL
# ============================================================


class ValidationResult(BaseModel):
    is_valid: bool = False
    missing_fields: List[str] = Field(default_factory=list)


class Shipment(BaseModel):
    request_id: str
    thread_id: Optional[str] = None  # Conversation root (FIRST message, never changes)
    last_message_id: Optional[str] = None  # Current head (LATEST message, always updated)
    customer_email: str
    subject: Optional[str] = None
    body: str
    status: str = "NEW"
    intent: Optional[str] = None
    translated_body: str
    translated_subject: str
    language_metadata: LanguageMetadata = Field(default_factory=LanguageMetadata)
    request_data: Dict = Field(default_factory=dict)
    validation_result: ValidationResult = Field(default_factory=ValidationResult)
    pricing_details: List[PricingSchema] = Field(default_factory=list)
    attachments: List[Attachment] = Field(default_factory=list)
    messages: List[Message] = Field(default_factory=list)
    message_ids: List[str] = Field(default_factory=list)
    final_document: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)