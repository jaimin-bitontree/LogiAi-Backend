"""
services/email/email_template.py

Common HTML email builder for all outgoing LogiAI emails.

Section rules:
  - "missing_info" : extracted_data  → missing_fields
  - "pricing"      : pricing (top)   → extracted_data
  - "status"       : status_banner   → extracted_data

Usage:
    from services.email.email_template import build_email
"""

from html import escape
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)
from typing import Literal, List, Optional
from models.shipment import PricingSchema

from config.constants import (
    PACKAGE_TYPES,
    CONTAINER_TYPES,
    INCOTERMS,
    SHIPMENT_TYPES,
    TRANSPORT_MODES,
    RTL_LANGUAGES,
)

# Create a mapping of field names to their available options
FIELD_OPTIONS = {
    "package_type": PACKAGE_TYPES,
    "container_type": CONTAINER_TYPES,
    "incoterm": INCOTERMS,
    "shipment_type": SHIPMENT_TYPES,
    "transport_mode": TRANSPORT_MODES
}

# ─────────────────────────────────────────────────────────────
# SECTION BUILDERS  (private)
# ─────────────────────────────────────────────────────────────

def _section_extracted_data(request_data: dict, all_fields: List[str]) -> str:
    """
    Always included in every email.
    Shows a table of all extracted (non-null) shipment fields.
    Fix #7 — html.escape() prevents HTML injection from LLM-extracted values.
    """
    # request_data contains {"required": {...}, "optional": {...}}
    # Flatten it first so we can loop over all fields cleanly
    flat_data = {
        **request_data.get("required", {}),
        **request_data.get("optional", {})
    }

    filled = {k: v for k, v in flat_data.items() if k in all_fields and v is not None}

    if not filled:
        return ""

    # Define categories based on schema field names
    categories = {
        "Basic Information": [
            "customer_name", "contact_person_name", "incoterm", "transport_mode"
        ],
        "Routing Details": [
            "origin_city", "origin_country", "origin_zip_code",
            "destination_city", "destination_country", "destination_zip_code"
        ],
        "Cargo Details": [
            "description_of_goods", "quantity", "cargo_weight", "package_type"
        ],
        "Additional Information": [
            "customer_street_number", "customer_zip_code", "customer_country"
        ]
    }

    html_blocks = []
    
    # Header for the entire section
    html_blocks.append('<h3 style="color:#27ae60;margin-top:24px;margin-bottom:16px;">✅ Shipment Details We Have</h3>')

    for section_title, keys in categories.items():
        # Only include rows that have actual extracted data for this category
        section_filled = {k: filled[k] for k in keys if k in filled}
        
        if not section_filled:
            continue

        rows = "".join(
            f"""<tr>
                  <td style="padding:7px 14px;border-bottom:1px solid #eee;
                             color:#555;font-weight:600;white-space:nowrap;width:40%;">
                    {escape(k.replace('_', ' ').title())}
                  </td>
                  <td style="padding:7px 14px;border-bottom:1px solid #eee;color:#333;">
                    {escape(str(v))}
                  </td>
                </tr>"""
            for k, v in section_filled.items()
        )

        # Build table for this section
        block = f"""
        <div style="margin-bottom:24px;">
            <h4 style="color:#2c3e50;margin-top:0;margin-bottom:8px;font-size:15px;border-bottom:2px solid #3498db;display:inline-block;padding-bottom:2px;">
                {section_title}
            </h4>
            <table style="width:100%;border-collapse:collapse;
                          border:1px solid #eee;border-radius:4px;overflow:hidden;background:#fff;">
              {rows}
            </table>
        </div>
        """
        html_blocks.append(block)

    return "".join(html_blocks)


def _section_missing_fields(missing_fields: List[str],field_options: dict = None) -> str:
    """
    Only shown in  missing_info  emails.
    Lists all required fields that are still missing.
    Fix #7 — html.escape() on field names.
    """
    if not missing_fields:
        return ""

    items = "".join(
        f'<li style="margin-bottom:6px;color:#c0392b;">'
        f'  {escape(f.replace("_", " ").title())}'
        f'</li>'
        for f in missing_fields
    )
    # Build field recommendations section
    recommendations_html = ""
    if field_options:
        recommendations_html = '<h3 style="color:#27ae60;margin-top:24px;">✓ Available Options</h3>'
        recommendations_html += '<p style="color:#555;">Here are the available options for the missing fields:</p>'
        recommendations_html += '<ul style="padding-left:20px;line-height:1.9;">'
        
        for field in missing_fields:
            if field in field_options:
                options = ", ".join(field_options[field])
                field_label = field.replace("_", " ").title()
                recommendations_html += f'<li style="margin-bottom:8px;"><strong>{escape(field_label)}:</strong> {escape(options)}</li>'
        
        recommendations_html += '</ul>'

    return f"""
    <h3 style="color:#e74c3c;margin-top:24px;">⚠️ Missing Information</h3>
    <p style="color:#555;">To process your request, we still need the following details:</p>
    <ul style="padding-left:20px;line-height:1.9;">
      {items}
    </ul>
    <p style="margin-top:16px;">
      Please <strong>reply to this email</strong> with the missing details
      and we will continue processing your shipment immediately.
    </p>
    {recommendations_html}
    """
def _section_pricing(pricing: PricingSchema) -> str:
    """
    Shows a comprehensive pricing breakdown.
    """
    if not pricing:
        return ""

    def _render_charge_table(title: str, charges: List) -> str:
        if not charges: return ""
        rows = "".join(
            f"""<tr>
                  <td style="padding:8px;border-bottom:1px solid #eee;color:#555;">{escape(c.description)}</td>
                  <td style="padding:8px;border-bottom:1px solid #eee;color:#333;text-align:right;">
                    {escape(c.amount)} {escape(c.currency)}
                    {f" ({escape(c.rate)}/{escape(c.basis)})" if c.rate and c.basis else ""}
                  </td>
                </tr>"""
            for c in charges
        )
        return f"""
        <div style="margin-top:20px;">
            <h4 style="color:#2c3e50;margin-bottom:8px;font-size:14px;border-bottom:1px solid #ddd;padding-bottom:4px;">{title}</h4>
            <table style="width:100%;border-collapse:collapse;font-size:13px;">{rows}</table>
        </div>
        """

    # Shipment details table (POL, POD, etc.)
    details = pricing.shipment_details
    details_html = ""
    if details:
        items = []
        if details.pol: items.append(f"<b>POL:</b> {escape(details.pol)}")
        if details.pod: items.append(f"<b>POD:</b> {escape(details.pod)}")
        if details.cargo_type: items.append(f"<b>Cargo:</b> {escape(details.cargo_type)}")
        if details.container_type: items.append(f"<b>Container:</b> {escape(details.container_type)}")
        
        if items:
            details_html = f"""
            <div style="background:#f0f4f8;padding:12px;border-radius:4px;font-size:13px;color:#2c3e50;margin-bottom:20px;">
                {" | ".join(items)}
            </div>
            """

    # Charge Tables
    main_freight = _render_charge_table("Main Freight Charges", pricing.main_freight_charges)
    origin       = _render_charge_table("Origin Charges",       pricing.origin_charges)
    dest         = _render_charge_table("Destination Charges",  pricing.destination_charges)
    additional   = _render_charge_table("Additional Charges",   pricing.additional_charges)

    # Payment Terms
    terms_html = ""
    if pricing.payment_terms and pricing.payment_terms.validity:
        terms_html = f"""
        <div style="margin-top:24px;padding:12px;background:#fff8e1;border-radius:4px;font-size:13px;border:1px solid #ffe082;">
            <b>Validity:</b> {escape(pricing.payment_terms.validity)}<br/>
            <b>Conditions:</b> {escape(pricing.payment_terms.conditions or "N/A")}
        </div>
        """

    notes_html = f'<p style="font-size:13px;color:#777;margin-top:16px;"><i>Note: {escape(pricing.calculation_notes)}</i></p>' if pricing.calculation_notes else ""

    # Calculate total costs
    def _safe_amount(c) -> float:
        try:
            if c.amount is None:
                return 0.0
            if isinstance(c.amount, str):
                return float(c.amount.replace(',', ''))
            return float(c.amount)
        except (ValueError, TypeError):
            return 0.0

    total_main = sum(_safe_amount(c) for c in pricing.main_freight_charges if c.amount)
    total_origin = sum(_safe_amount(c) for c in pricing.origin_charges if c.amount)
    total_dest = sum(_safe_amount(c) for c in pricing.destination_charges if c.amount)
    total_additional = sum(_safe_amount(c) for c in pricing.additional_charges if c.amount)
    
    grand_total = total_main + total_origin + total_dest + total_additional
    currency = pricing.main_freight_charges[0].currency if pricing.main_freight_charges else "USD"
    
    # Total summary section
    total_summary_html = f"""
    <div style="margin-top:32px;padding:20px;background:#f0f9ff;border:2px solid #3498db;border-radius:6px;">
        <h3 style="color:#2c3e50;margin-top:0;margin-bottom:16px;text-align:center;">💰 Total Cost Summary</h3>
        <table style="width:100%;font-size:14px;">
            <tr>
                <td style="padding:8px;color:#555;">Main Freight Charges:</td>
                <td style="padding:8px;text-align:right;font-weight:600;">{total_main:,.2f} {escape(currency)}</td>
            </tr>
            <tr>
                <td style="padding:8px;color:#555;">Origin Charges:</td>
                <td style="padding:8px;text-align:right;font-weight:600;">{total_origin:,.2f} {escape(currency)}</td>
            </tr>
            <tr>
                <td style="padding:8px;color:#555;">Destination Charges:</td>
                <td style="padding:8px;text-align:right;font-weight:600;">{total_dest:,.2f} {escape(currency)}</td>
            </tr>
            <tr>
                <td style="padding:8px;color:#555;">Additional Charges:</td>
                <td style="padding:8px;text-align:right;font-weight:600;">{total_additional:,.2f} {escape(currency)}</td>
            </tr>
            <tr style="border-top:2px solid #3498db;">
                <td style="padding:12px 8px;color:#2c3e50;font-size:16px;font-weight:700;">GRAND TOTAL:</td>
                <td style="padding:12px 8px;text-align:right;color:#2980b9;font-size:18px;font-weight:700;">{grand_total:,.2f} {escape(currency)}</td>
            </tr>
        </table>
    </div>
    """

    return f"""
    <div style="margin-top:24px;">
        <h3 style="color:#2980b9;margin-bottom:16px;border-left:4px solid #2980b9;padding-left:12px;">💰 Quotation Details</h3>
        {details_html}
        {main_freight}
        {origin}
        {dest}
        {additional}
        {terms_html}
        {total_summary_html}
        {notes_html}
    </div>
    <div style="margin-top:24px;text-align:center;">
       <p style="color:#555;">To confirm this quote, please reply with <strong>"CONFIRM"</strong></p>
    </div>
    """


def _section_status(status: str, message: Optional[str]) -> str:
    """
    Only shown in  status  emails — rendered above extracted data.
    Shows a coloured status badge + optional custom message.
    Fix #7 — html.escape() on message text.
    """
    STATUS_COLORS = {
        "NEW":             "#3498db",
        "MISSING_INFO":    "#e67e22",
        "PRICING_PENDING": "#9b59b6",
        "QUOTED":          "#2980b9",
        "CONFIRMED":       "#27ae60",
        "CLOSED":          "#7f8c8d",
        "CANCELLED":       "#e74c3c",
    }
    color     = STATUS_COLORS.get(status, "#3498db")
    msg_block = ""
    if message:
        # Styled description card matching the clean border-left UI
        msg_block = f"""
        <div style="background:#f8f9fa;padding:16px 20px;border-left:4px solid {color};
                    border-radius:0 6px 6px 0;margin-top:28px;">
            <div style="color:{color};margin:0;font-size:15px;line-height:1.5;">
                <span style="margin-right:8px;font-weight:bold;">✓</span> {escape(message)}
            </div>
        </div>
        """

    return f"""
    <div style="text-align:center;margin-top:16px;">
      <h3 style="color:{color};margin-bottom:12px;font-size:18px;margin-top:0;">📦 Shipment Status Update</h3>
      <div style="display:inline-block;padding:6px 18px;background:{color};
                  color:#fff;border-radius:20px;font-weight:bold;font-size:12px;
                  letter-spacing:1px;">
        {escape(status.replace('_', ' '))}
      </div>
    </div>
    {msg_block}
    """


def _section_spam_rejection() -> str:
    """Spam rejection message template"""
    return """
    <div style="background:#f8f9fa;padding:24px;border-radius:6px;margin-bottom:24px;">
        <h3 style="margin-top:0;color:#2c3e50;">Thank You for Your Email</h3>
        
        <p style="color:#555;line-height:1.6;">
            We appreciate you reaching out to LogiAI. However, we are unable to process your request 
            as it does not appear to be related to our logistics services.
        </p>
        
        <p style="color:#555;line-height:1.6;">
            If you believe this is an error or have a legitimate shipment inquiry, 
            please reply to this email with clear details about your shipment requirements, including:
        </p>
        
        <ul style="color:#555;line-height:1.8;">
            <li>Origin location (city, country)</li>
            <li>Destination location (city, country)</li>
            <li>Cargo details (weight, dimensions, type)</li>
            <li>Preferred transport mode (Sea, Air, Road, Rail)</li>
        </ul>
        
        <p style="color:#555;line-height:1.6;">
            Our team will be happy to assist you with your logistics needs.
        </p>
        
        <p style="color:#888;font-size:14px;margin-top:24px;">
            Best regards,<br>
            <strong>LogiAI Team</strong><br>
            Intelligent Logistics Management
        </p>
    </div>
    """


def _section_notification_reminder() -> str:
    """Generate notification reminder section."""
    return """
    <div style="background:#e8f4fd;border:1px solid #bee3f8;border-radius:6px;padding:20px;margin-bottom:20px;">
        <h3 style="color:#2b6cb0;margin-top:0;margin-bottom:12px;font-size:18px;">
            🔔 Quote Reminder
        </h3>
        <p style="color:#2c5282;margin:0;font-size:15px;line-height:1.6;">
            This is a friendly reminder that your quote is ready for review. 
            Please find the complete pricing details below and let us know if you have any questions or would like to proceed.
        </p>
    </div>
    """


def _section_pricing_details(pricing_details: Optional[List] = None) -> str:
    """Generate pricing details section for notifications."""
    if not pricing_details:
        return ""
    
    pricing_html = ""
    for pricing in pricing_details:
        # Convert dict to PricingSchema object if needed
        if isinstance(pricing, dict):
            from models.shipment import PricingSchema
            try:
                pricing_obj = PricingSchema(**pricing)
                pricing_html += _section_pricing(pricing_obj)
            except Exception as e:
                logger.warning(f"Failed to convert pricing dict to PricingSchema: {e}")
                continue
        elif hasattr(pricing, 'model_dump'):
            # Already a Pydantic object
            pricing_html += _section_pricing(pricing)
        else:
            # Unknown format, skip
            continue
    
    return pricing_html


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

from models.shipment import PricingSchema

def build_email(
    email_type:    Literal["missing_info", "pricing", "status", "spam", "notification"],
    customer_name: str = "",
    request_id:    str = "",

    # Always included — shown in every email
    request_data:  Optional[dict]      = None,
    all_fields:    Optional[List[str]] = None,

    # missing_info only
    missing_fields: Optional[List[str]] = None,
    field_options: Optional[dict] = None,
    # pricing only (Uses PricingSchema object)
    pricing: Optional[PricingSchema] = None,
    
    # notification only
    pricing_details: Optional[List] = None,

    # status only
    status:  Optional[str] = None,
    message: Optional[str] = None,
    
    # Custom next steps list
    next_steps: Optional[List[str]] = None,
    
    # spam only
    customer_email: Optional[str] = None,
    subject: Optional[str] = None,

    # Language for RTL support
    lang: Optional[str] = "en",
) -> str:
    """
    Build a full HTML email body for any outgoing LogiAI email.

    Section order per type:
      missing_info : extracted_data  →  missing_fields
      pricing      : pricing (top)   →  extracted_data
      status       : status_banner   →  extracted_data
      spam         : spam_rejection
    """
    # Handle spam emails separately
    if email_type == "spam":
        return f"""
        <html>
        <body style="font-family:Arial,sans-serif;color:#333;
                     max-width:660px;margin:auto;padding:28px;background-color:#f9f9f9;">

          <div style="background:#fff;border:1px solid #ddd;border-radius:6px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.05);">
            
            <!-- Header -->
            <div style="padding:32px 24px 20px;text-align:center;">
              <h1 style="color:#2c3e50;margin:0;font-size:26px;font-weight:600;">
                LogiAI — Shipment Management
              </h1>
            </div>

            <hr style="border:none;border-top:1px solid #eee;margin:0;">

            <!-- Content -->
            <div style="padding:28px 24px;">
              {_section_spam_rejection()}
            </div>
          </div>

        </body>
        </html>
        """
    
    _rd  = request_data or {}
    _af  = all_fields   or []
    data_section = _section_extracted_data(_rd, _af)

    # ── Assemble sections in type-specific order ──────────────
    if email_type == "missing_info":
        body = data_section + _section_missing_fields(missing_fields or [], field_options)

    elif email_type == "pricing":
        body = _section_pricing(pricing) + data_section

    elif email_type == "status":
        body = _section_status(status or "", message) + data_section
    
    elif email_type == "notification":
        body = _section_notification_reminder() + _section_pricing_details(pricing_details) + data_section

    else:
        body = data_section

    # ── Wrap in base HTML layout ──────────────────────────────
    safe_name   = escape(customer_name or "Customer")
    safe_id     = escape(request_id)

    # RTL support for Arabic, Hebrew, Urdu, Persian
    is_rtl      = (lang or "en") in RTL_LANGUAGES
    dir_attr    = 'dir="rtl"' if is_rtl else ''
    align_style = "text-align:right;" if is_rtl else ""

    # Operator specific instruction block
    operator_instruction = ""
    if email_type == "pricing" and not pricing:
        operator_instruction = f"""
        <div style="background:#fff3cd;padding:16px;border-left:4px solid #ffecb5;margin-bottom:20px;border-radius:4px;">
            <h4 style="color:#856404;margin-top:0;margin-bottom:8px;">🔔 Action Required</h4>
            <p style="color:#856404;margin:0;font-size:14px;">
                Please review the extracted shipment details below and reply to this email with the pricing quotation. 
                Format your reply clearly so the AI can extract the pricing information.
            </p>
            <p style="color:#856404;margin:8px 0 0 0;font-size:13px;font-weight:600;">
                Request ID: {safe_id}
            </p>
        </div>
        """

    # Next Steps Block
    next_steps_html = ""
    if next_steps:
        steps_list = "".join(f'<li style="margin-bottom:12px;color:#333;"><span style="color:#3498db;margin-right:8px;font-weight:bold;">▪</span>{escape(step)}</li>' for step in next_steps)
        next_steps_html = f"""
        <div style="background:#f8f9fa;border-radius:6px;padding:24px;margin-top:32px;margin-bottom:20px;">
            <h4 style="color:#2c3e50;margin-top:0;margin-bottom:16px;font-size:16px;">Next Steps:</h4>
            <ul style="list-style-type:none;padding-left:10px;margin:0;">
                {steps_list}
            </ul>
        </div>
        """

    # Keep Request ID Handy Block
    keep_handy_html = f"""
    <div style="background:#fff7f0;padding:16px 20px;border-left:4px solid #e67e22;border-radius:0 6px 6px 0;margin-top:20px;">
        <span style="margin-right:8px;">📝</span>
        <span style="color:#d35400;font-size:14px;">Please keep your Request ID handy for future reference.</span>
    </div>
    """

    return f"""
    <html>
    <body {dir_attr} style="font-family:Arial,sans-serif;color:#333;{align_style}
                 max-width:660px;margin:auto;padding:28px;background-color:#f9f9f9;">

      <div {dir_attr} style="background:#fff;border:1px solid #ddd;border-radius:6px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.05);">
        
        <!-- Header -->
        <div style="padding:32px 24px 20px;text-align:center;">
          <h1 style="color:#2c3e50;margin:0;font-size:26px;font-weight:600;">
            LogiAI — Shipment Management
          </h1>
          <div style="margin-top:10px;font-size:16px;color:#7f8c8d;">
            Request ID: <span style="color:#3498db;font-weight:600;">{safe_id}</span>
          </div>
        </div>

        <hr style="border:none;border-top:1px solid #eee;margin:0;">

        <!-- Content -->
        <div style="padding:28px 24px;">

          <p style="margin-top:0;">Dear <strong>{safe_name}</strong>,</p>
          
          {operator_instruction}

          {body}
          
          <div style="margin-top:32px;color:#555;font-size:15px;line-height:1.6;">
            We appreciate your trust in our services and look forward to
            handling your shipment with the utmost care and professionalism.
          </div>

          <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
          
          <div style="color:#555;font-size:15px;">
            <div style="margin-bottom:4px;">Best regards,</div>
            <div style="color:#2c3e50;font-size:16px;font-weight:600;margin-bottom:20px;">Your Freight Team</div>
            
            <div style="color:#7f8c8d;font-size:14px;line-height:1.6;">
              <p style="margin:0 0 8px 0;">
                <span style="color:#3498db;font-size:16px;margin-right:6px;">&#9993;</span>For any queries, please reply to this email
              </p>
              <p style="margin:0;">
                <span style="font-size:16px;margin-right:6px;">🔔</span>Include your Request ID: {safe_id} in all communications
              </p>
            </div>
          </div>
        </div>
      </div>

    </body>
    </html>
    """