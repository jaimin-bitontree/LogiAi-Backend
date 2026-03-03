import re
from typing import List, Dict


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
        disposition = str(part.get("Content-Disposition", ""))

        if "attachment" in disposition:
            attachments.append({
                "filename": part.get_filename(),
                "content_type": part.get_content_type(),
            })

    return attachments
