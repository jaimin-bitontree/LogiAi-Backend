import email
import re
from typing import List, Dict


def extract_message_id(raw_email: bytes) -> str | None:
    """Parse the Message-ID header from raw RFC822 email bytes.
    Strips angle brackets to match the format stored in DB by parse_node.
    """
    msg = email.message_from_bytes(raw_email)
    raw_id = msg.get("Message-ID", "").strip().strip("<>")
    return raw_id or None


def extract_email_address(raw: str) -> str:
    match = re.search(r"<([^>]+)>", raw or "")
    if match:
        return match.group(1).strip().lower()
    return (raw or "").strip().lower()


def extract_body(msg) -> str:
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))

            if (
                content_type == "text/plain" and
                "attachment" not in disposition
            ):
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="ignore")
                break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="ignore")

    return body.strip()


def clean_email_body(body: str) -> str:
    if not body:
        return ""

    body = re.split(r"On .* wrote:", body)[0]
    body = re.split(r"From: .*", body)[0]
    body = re.sub(r"\n\s*\n", "\n\n", body)

    return body.strip()


def extract_attachments(msg) -> List[Dict]:
    attachments = []

    for part in msg.walk():
        content_type = part.get_content_type()
        disposition = str(part.get("Content-Disposition", ""))
        filename = part.get_filename()

        # Many PDFs are marked as "inline" or have no disposition but are application/pdf
        is_attachment = "attachment" in disposition
        is_pdf = content_type == "application/pdf"

        if is_attachment or is_pdf:
            # Fallback for filename if get_filename() is None (common for some clients)
            if not filename and is_pdf:
                filename = f"document_{len(attachments) + 1}.pdf"
            
            if filename:
                attachments.append({
                    "filename": filename,
                    "content_type": content_type,
                })

    return attachments
