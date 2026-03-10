from enum import Enum

# ===============================
# EMAIL INTENT ENUM
# ===============================

class EmailIntent(str, Enum):
    OPERATOR_PRICING = "operator_pricing"
    NEW_REQUEST = "new_request"
    STATUS_INQUIRY = "status_inquiry"
    CONFIRMATION = "confirmation"
    CANCELLATION = "cancellation"
    MISSING_INFORMATION = "missing_information"


# ===============================
# STATUS ENUM
# ===============================

STATUSES = [
    "NEW",
    "MISSING_INFO",
    "PRICING_PENDING",
    "QUOTED",
    "CONFIRMED",
    "CLOSED",
    "CANCELLED",
]


# ===============================
# REQUIRED FIELDS
# ===============================

REQUIRED_FIELDS = [
    "customer_name",
    "customer_street_number",
    "customer_zip_code",
    "customer_country",
    "origin_zip_code",
    "origin_city",
    "origin_country",
    "destination_zip_code",
    "destination_city",
    "destination_country",
    "incoterm",
    "quantity",
    "package_type",
    "cargo_weight",
    "volume",
    "container_type",
    "transport_mode",
    "shipment_type",
]


# ===============================
# OPTIONAL FIELDS
# ===============================

OPTIONAL_FIELDS = [
    "contact_person_name",
    "contact_person_email",
    "contact_person_phone",
    "customer_reference",
    "origin_company",
    "origin_street_number",
    "destination_company",
    "destination_street_number",
    "description_of_goods",
    "additional_information",
    "stackable",
    "dangerous",
    "temperature",
    "length",
    "height",
    "width",
]


# ===============================
# ENUMS / ALLOWED VALUES
# ===============================

INCOTERMS = [
    "CFR", "CIF", "CIP", "CPT",
    "DAP", "DDP", "DPU",
    "EXW", "FAS", "FCA","FOB"
]

PACKAGE_TYPES = [
    "Bag", "Bulk Bag", "Bundle", "Bottle",
    "Box", "Basket", "Container", "Carton",
    "Envelope", "Mix", "Piece", "Package",
    "Pallet", "Tube", "Unit", "PCS"
]

SHIPMENT_TYPES = [
    "LCL",
    "FCL",
    "AIR"
]

TRANSPORT_MODES = [
    "Sea",
    "Air",
    "Road",
    "Rail"
]

CONTAINER_TYPES = [
    "20' GP",
    "20' High Cube",
    "20' Flatrack",
    "20' Open Top",
    "20' Open Top High Cube",
    "20' Reefer",
    "20' Tank Container",
    "40' GP",
    "40' High Cube",
    "40' Flatrack",
    "40' Open Top",
    "40' Open Top High Cube",
    "40' Reefer",
    "40' Tank Container",
    "45' GP",
    "45' High Cube",
]