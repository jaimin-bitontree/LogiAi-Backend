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

    rows = "".join(
        f"""<tr>
              <td style="padding:7px 14px;border-bottom:1px solid #eee;
                         color:#555;font-weight:600;white-space:nowrap;">
                {escape(k.replace('_', ' ').title())}
              </td>
              <td style="padding:7px 14px;border-bottom:1px solid #eee;color:#333;">
                {escape(str(v))}
              </td>
            </tr>"""
        for k, v in filled.items()
    )

    return f"""
    <h3 style="color:#27ae60;margin-top:24px;">✅ Shipment Details We Have</h3>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px;
                  border:1px solid #eee;border-radius:4px;overflow:hidden;">
      {rows}
    </table>
    """


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
    msg_block = (
        f'<p style="margin-top:12px;color:#555;">{escape(message)}</p>'
        if message else ""
    )

    return f"""
    <h3 style="color:{color};margin-top:24px;">📦 Shipment Status Update</h3>
    <div style="display:inline-block;padding:8px 20px;background:{color};
                color:#fff;border-radius:4px;font-weight:bold;font-size:14px;
                letter-spacing:0.5px;">
      {escape(status.replace('_', ' '))}
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
    
    # Optional greeting for operators
    greeting = f'<p>Dear <strong>{safe_name}</strong>,</p>'
    if email_type == "pricing" and not request_data:
        # If request_data is None it implies it's going to the customer,
        # but in this flow, pricing email with no pricing_details is sent to the operator.
        # So we add a specific operator greeting if we pass a flag,
        # or we just use the customer_name (which is "Operator" in some cases).
        pass

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

    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;color:#333;
                 max-width:660px;margin:auto;padding:28px;">

      <!-- Header -->
      <div style="background:#2c3e50;padding:18px 24px;border-radius:6px 6px 0 0;text-align:center;">
        <h1 style="color:#fff;margin:0;font-size:20px;">
          LogiAI — Shipment Management
        </h1>
        <div style="margin-top:8px;display:inline-block;background:rgba(255,255,255,0.2);padding:4px 12px;border-radius:12px;font-size:13px;color:#ecf0f1;font-family:monospace;">
          #{safe_id}
        </div>
      </div>

      <!-- Content -->
      <div style="border:1px solid #ddd;border-top:none;
                  padding:24px;border-radius:0 0 6px 6px;">

        <p>Dear <strong>{safe_name}</strong>,</p>
        
        {operator_instruction}

        {body}

        <hr style="border:none;border-top:1px solid #eee;margin:28px 0;">
        <p style="font-size:12px;color:#aaa;text-align:center;">
          Automated message from LogiAI.
        </p>
      </div>

    </body>
    </html>
    """
