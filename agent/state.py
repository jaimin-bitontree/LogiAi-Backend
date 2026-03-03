from typing import Optional, Dict, List
from typing_extensions import TypedDict


class AgentState(TypedDict):
    raw_email: bytes
    request_id:        str
    thread_id:         Optional[str]
    customer_email:    str
    subject:           Optional[str]
    message_ids:       List[str]
    status:            str
    intent:            Optional[str]
    attachments:       Dict
