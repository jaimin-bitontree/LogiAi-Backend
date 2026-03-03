from email import policy
from email.parser import BytesParser
from utils.email_utils import (
    extract_email_address,
    extract_body,
    clean_email_body,
    extract_attachments,
)
from agent.state import AgentState


def parser_node(state: AgentState) -> AgentState:

    raw_email = state["raw_email"]
    msg = BytesParser(policy=policy.default).parsebytes(raw_email)

    # Subject
    subject = msg.get("Subject", "")

    # Sender
    sender_raw = msg.get("From", "")
    customer_email = extract_email_address(sender_raw)

    # IDs
    message_id = (msg.get("Message-ID", "") or "").strip().strip("<>")
    in_reply_to = msg.get("In-Reply-To", "")
    thread_id = in_reply_to.strip().strip("<>") if in_reply_to else None

    # Body
    raw_body = extract_body(msg)
    clean_body = clean_email_body(raw_body)

    # Attachments (now dict format)
    attachments = extract_attachments(msg)

    # Update state
    state.update({
        "message_id": message_id,
        "thread_id": thread_id,
        "customer_email": customer_email,
        "subject": subject,
        "body": clean_body,
        "attachments": attachments,
    })

    return state
