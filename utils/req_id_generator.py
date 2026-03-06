from datetime import datetime


def generate_request_id() -> str:
    now = datetime.utcnow()

    year = now.strftime("%Y")
    timestamp = now.strftime("%m%d%H%M%S%f")

    return f"REQ-{year}-{timestamp}"
