import imaplib
import email
import os
import re
from email.header import decode_header
from dotenv import load_dotenv

load_dotenv()

GMAIL_ADDRESS      = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


def connect_gmail() -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    mail.select("inbox")
    print("this is email fetch")
    print(mail)
    return mail


def decode_str(value, encoding=None) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode(encoding or "utf-8", errors="ignore")
        except:
            return value.decode("latin-1", errors="ignore")
    return value or ""


def extract_email_address(raw: str) -> str:
    match = re.search(r"<([^>]+)>", raw or "")
    if match:
        return match.group(1).strip().lower()
    return (raw or "").strip().lower()


def extract_message_id(msg) -> str:
    message_id = msg.get("Message-ID", "")
    return message_id.strip().strip("<>") if message_id else ""


def extract_thread_id(msg) -> str | None:
    in_reply_to = msg.get("In-Reply-To", "")
    if in_reply_to:
        return in_reply_to.strip().strip("<>")
    return None


def get_email_body(msg) -> str:
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition  = str(part.get("Content-Disposition", ""))

            if content_type == "text/plain" and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                body    = payload.decode(charset, errors="ignore")
                break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body    = payload.decode(charset, errors="ignore")

    return body.strip()


def get_attachments(msg) -> dict:
    saved = {}
    os.makedirs("uploads", exist_ok=True)

    for part in msg.walk():
        disposition = str(part.get("Content-Disposition", ""))

        if "attachment" in disposition:
            filename = part.get_filename()
            if filename:
                decoded, enc = decode_header(filename)[0]
                filename     = decode_str(decoded, enc)
                filename     = filename.replace(" ", "_")
                filepath     = os.path.join("uploads", filename)

                with open(filepath, "wb") as f:
                    f.write(part.get_payload(decode=True))

                saved[filename] = filepath
                print(f"   📎 Attachment saved: {filename}")

    return saved


def mark_as_read(mail: imaplib.IMAP4_SSL, email_id: bytes):
    mail.store(email_id, "+FLAGS", "\\Seen")


def fetch_unread_emails() -> list:
    emails = []

    try:
        mail = connect_gmail()

        status, message_ids = mail.search(None, "UNSEEN")
        

        if status != "OK" or not message_ids[0]:
            print("   📭 No new emails")
            mail.logout()
            return []

        ids = message_ids[0].split()
        print(ids)
        print(f"   📬 Found {len(ids)} new email(s)")

        for email_id in ids:
            print(email_id)
            status, data = mail.fetch(email_id, "(RFC822)")

            if status != "OK":
                continue

            raw_email = data[0][1]
            msg       = email.message_from_bytes(raw_email)

            subject_raw, enc = decode_header(
                msg.get("Subject", "No Subject")
            )[0]
            subject = decode_str(subject_raw, enc)

            sender_raw   = msg.get("From", "")
            sender_email = extract_email_address(sender_raw)
            message_id   = extract_message_id(msg)
            thread_id    = extract_thread_id(msg)
            body         = get_email_body(msg)
            attachments  = get_attachments(msg)

            mark_as_read(mail, email_id)

            parsed = {
                "sender_email": sender_email,
                "subject":      subject,
                "body":         body,
                "message_id":   message_id,
                "thread_id":    thread_id,
                "attachments":  attachments,
                "raw_sender":   sender_raw
            }

            print(f"   ✅ Parsed: {sender_email} — {subject[:40]}")
            emails.append(parsed)

        mail.logout()

    except imaplib.IMAP4.error as e:
        print(f"   ❌ IMAP error: {e}")

    except Exception as e:
        print(f"   ❌ Gmail receiver error: {e}")

    return emails