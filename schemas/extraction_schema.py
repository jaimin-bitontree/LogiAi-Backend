from pydantic import BaseModel, field_validator
from typing import Optional
from core.constants import (
    INCOTERMS,
    PACKAGE_TYPES,
    SHIPMENT_TYPES,
    TRANSPORT_MODES,
    CONTAINER_TYPES,
)


class ExtractionSchema(BaseModel):

    # ===============================
    # REQUIRED FIELDS
    # ===============================
    customer_name:           Optional[str]   = None
    customer_street_number:  Optional[str]   = None
    customer_zip_code:       Optional[str]   = None
    customer_country:        Optional[str]   = None
    origin_zip_code:         Optional[str]   = None
    origin_city:             Optional[str]   = None
    origin_country:          Optional[str]   = None
    destination_zip_code:    Optional[str]   = None
    destination_city:        Optional[str]   = None
    destination_country:     Optional[str]   = None
    incoterm:                Optional[str]   = None
    quantity:                Optional[int]   = None
    package_type:            Optional[str]   = None
    cargo_weight:            Optional[float] = None
    volume:                  Optional[float] = None
    length:                  Optional[float] = None
    height:                  Optional[float] = None
    width:                   Optional[float] = None
    container_type:          Optional[str]   = None
    transport_mode:          Optional[str]   = None
    shipment_type:           Optional[str]   = None

    # ===============================
    # OPTIONAL FIELDS
    # ===============================
    contact_person_name:         Optional[str]   = None
    contact_person_email:        Optional[str]   = None
    contact_person_phone:        Optional[str]   = None
    customer_reference:          Optional[str]   = None
    origin_company:              Optional[str]   = None
    origin_street_number:        Optional[str]   = None
    destination_company:         Optional[str]   = None
    destination_street_number:   Optional[str]   = None
    description_of_goods:        Optional[str]   = None
    additional_information:      Optional[str]   = None
    stackable:                   Optional[bool]  = None
    dangerous:                   Optional[bool]  = None
    temperature:                 Optional[float]   = None

    # ===============================
    # ENUM VALIDATORS
    # ===============================
    @field_validator("incoterm")
    @classmethod
    def validate_incoterm(cls, v):
        if v and v not in INCOTERMS:
            raise ValueError(f"Invalid incoterm '{v}'. Allowed: {INCOTERMS}")
        return v

    @field_validator("package_type")
    @classmethod
    def validate_package_type(cls, v):
        if v and v not in PACKAGE_TYPES:
            raise ValueError(f"Invalid package_type '{v}'. Allowed: {PACKAGE_TYPES}")
        return v

    @field_validator("shipment_type")
    @classmethod
    def validate_shipment_type(cls, v):
        if v and v not in SHIPMENT_TYPES:
            raise ValueError(f"Invalid shipment_type '{v}'. Allowed: {SHIPMENT_TYPES}")
        return v

    @field_validator("transport_mode")
    @classmethod
    def validate_transport_mode(cls, v):
        if v and v not in TRANSPORT_MODES:
            raise ValueError(f"Invalid transport_mode '{v}'. Allowed: {TRANSPORT_MODES}")
        return v

    @field_validator("container_type")
    @classmethod
    def validate_container_type(cls, v):
        if v and v not in CONTAINER_TYPES:
            raise ValueError(f"Invalid container_type '{v}'. Allowed: {CONTAINER_TYPES}")
        return v