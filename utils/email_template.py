"""
utils/email_template.py

Common HTML email builder for all outgoing LogiAI emails.

Section rules:
  - "missing_info" : extracted_data  → missing_fields
  - "pricing"      : pricing (top)   → extracted_data
  - "status"       : status_banner   → extracted_data

Usage:
    from utils.email_template import build_email
"""

from html import escape
from typing import Literal, List, Optional


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


def _section_missing_fields(missing_fields: List[str]) -> str:
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
    """


def _section_pricing(pricing_details: List[dict]) -> str:
    """
    Only shown in  pricing  emails — rendered at top before extracted data.
    Shows a pricing breakdown table.
    Fix #7 — html.escape() on all values.
    """
    if not pricing_details:
        return ""

    rows = "".join(
        f"""<tr>
              <td style="padding:8px 14px;border-bottom:1px solid #eee;
                         color:#555;font-weight:600;">
                {escape(str(p.get('transport_mode', 'N/A')))}
              </td>
              <td style="padding:8px 14px;border-bottom:1px solid #eee;color:#333;">
                {escape(str(p.get('amount', 'N/A')))} {escape(str(p.get('currency', '')))}
              </td>
              <td style="padding:8px 14px;border-bottom:1px solid #eee;color:#777;
                         font-size:13px;">
                {escape(str(p.get('notes', '—')))}
              </td>
            </tr>"""
        for p in pricing_details
    )

    return f"""
    <h3 style="color:#2980b9;margin-top:24px;">💰 Your Quotation</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px;
                  border:1px solid #eee;">
      <thead>
        <tr style="background:#f0f4f8;">
          <th style="padding:8px 14px;text-align:left;color:#333;">Transport Mode</th>
          <th style="padding:8px 14px;text-align:left;color:#333;">Amount</th>
          <th style="padding:8px 14px;text-align:left;color:#333;">Notes</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <p style="color:#555;">
      To confirm this quote, please reply with <strong>"CONFIRM"</strong>
      or contact your LogiAI operator directly.
    </p>
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


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def build_email(
    email_type:    Literal["missing_info", "pricing", "status"],
    customer_name: str,
    request_id:    str,

    # Always included — shown in every email
    request_data:  Optional[dict]      = None,
    all_fields:    Optional[List[str]] = None,

    # missing_info only
    missing_fields: Optional[List[str]] = None,

    # pricing only
    pricing_details: Optional[List[dict]] = None,

    # status only
    status:  Optional[str] = None,
    message: Optional[str] = None,
    
    # Custom next steps list
    next_steps: Optional[List[str]] = None,
) -> str:
    """
    Build a full HTML email body for any outgoing LogiAI email.

    Section order per type:
      missing_info : extracted_data  →  missing_fields
      pricing      : pricing (top)   →  extracted_data
      status       : status_banner   →  extracted_data
    """
    _rd  = request_data or {}
    _af  = all_fields   or []
    data_section = _section_extracted_data(_rd, _af)

    # ── Assemble sections in type-specific order ──────────────
    if email_type == "missing_info":
        body = data_section + _section_missing_fields(missing_fields or [])

    elif email_type == "pricing":
        body = _section_pricing(pricing_details or []) + data_section

    elif email_type == "status":
        body = _section_status(status or "", message) + data_section

    else:
        body = data_section

    # ── Wrap in base HTML layout ──────────────────────────────
    safe_name = escape(customer_name or "Customer")
    safe_id   = escape(request_id)

    # Operator specific instruction block
    operator_instruction = ""
    if email_type == "pricing" and not pricing_details:
        operator_instruction = f"""
        <div style="background:#fff3cd;padding:16px;border-left:4px solid #ffecb5;margin-bottom:20px;border-radius:4px;">
            <h4 style="color:#856404;margin-top:0;margin-bottom:8px;">🔔 Action Required</h4>
            <p style="color:#856404;margin:0;font-size:14px;">
                Please review the extracted shipment details below and reply to this email with the pricing quotation. 
                Format your reply clearly so the AI can extract the pricing information.
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
    <body style="font-family:Arial,sans-serif;color:#333;
                 max-width:660px;margin:auto;padding:28px;background-color:#f9f9f9;">

      <div style="background:#fff;border:1px solid #ddd;border-radius:6px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.05);">
        
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
