from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, Union
from config.constants import (
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
    customer_name:           Optional[str] = None
    customer_street_number:  Optional[str] = None
    customer_zip_code:       Optional[str] = None
    customer_country:        Optional[str] = None
    origin_zip_code:         Optional[str] = None
    origin_city:             Optional[str] = None
    origin_country:          Optional[str] = None
    destination_zip_code:    Optional[str] = None
    destination_city:        Optional[str] = None
    destination_country:     Optional[str] = None
    incoterm:                Optional[str] = None
    quantity:                Optional[int] = None
    package_type:            Optional[str] = None
    # Accept int/float from LLM — model_validator converts to str
    cargo_weight:            Optional[Union[str, int, float]] = None
    volume:                  Optional[Union[str, int, float]] = None
    length:                  Optional[Union[str, int, float]] = None
    height:                  Optional[Union[str, int, float]] = None
    width:                   Optional[Union[str, int, float]] = None
    container_type:          Optional[str] = None
    transport_mode:          Optional[str] = None
    shipment_type:           Optional[str] = None

    # ===============================
    # OPTIONAL FIELDS
    # ===============================
    contact_person_name:         Optional[str] = None
    contact_person_email:        Optional[str] = None
    contact_person_phone:        Optional[str] = None
    customer_reference:          Optional[str] = None
    origin_company:              Optional[str] = None
    origin_street_number:        Optional[str] = None
    destination_company:         Optional[str] = None
    destination_street_number:   Optional[str] = None
    description_of_goods:        Optional[str] = None
    additional_information:      Optional[str] = None
    stackable:                   Optional[bool] = None
    dangerous:                   Optional[bool] = None
    temperature:                 Optional[Union[float, str]] = None

    # ===============================
    # VALIDATORS
    # ===============================
    @field_validator("customer_street_number", "origin_street_number", "destination_street_number",
                     "customer_zip_code", "origin_zip_code", "destination_zip_code")
    @classmethod
    def coerce_zip_street_to_str(cls, v):
        return str(v) if v is not None else v

    @model_validator(mode="after")
    def coerce_numeric_fields_to_str(self):
        """Convert numeric weight/dimension fields to str after model creation."""
        for field in ("cargo_weight", "volume", "length", "height", "width"):
            val = getattr(self, field)
            if val is not None and not isinstance(val, str):
                setattr(self, field, str(val))
        return self

    @field_validator("incoterm")
    @classmethod
    def validate_incoterm(cls, v):
        if v and v not in INCOTERMS:
            return None
        return v

    @field_validator("package_type")
    @classmethod
    def validate_package_type(cls, v):
        if v and v not in PACKAGE_TYPES:
            return None
        return v

    @field_validator("shipment_type")
    @classmethod
    def validate_shipment_type(cls, v):
        if v and v not in SHIPMENT_TYPES:
            return None
        return v

    @field_validator("transport_mode")
    @classmethod
    def validate_transport_mode(cls, v):
        if v and v not in TRANSPORT_MODES:
            return None
        return v

    @field_validator("container_type")
    @classmethod
    def validate_container_type(cls, v):
        if v and v not in CONTAINER_TYPES:
            return None
        return v
