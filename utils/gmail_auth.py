"""
utils/gmail_auth.py

Gmail API OAuth2 authentication helper.
Loads credentials from token.json (local) or GMAIL_TOKEN_JSON env var (Render).
"""

import os
import json
import logging
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


def get_gmail_service():
    """
    Returns an authenticated Gmail API service.
    - Local: reads token.json from project root
    - Render: reads GMAIL_TOKEN_JSON environment variable
    """
    creds = None

    # 1. Try env var first (Render production)
    token_json_str = os.getenv("GMAIL_TOKEN_JSON")
    if token_json_str:
        try:
            token_data = json.loads(token_json_str)
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            logger.debug("Loaded credentials from GMAIL_TOKEN_JSON env var")
        except Exception as e:
            logger.error(f"Failed to load GMAIL_TOKEN_JSON: {e}")
            raise RuntimeError(f"Invalid GMAIL_TOKEN_JSON: {e}") from e

    # 2. Fall back to token.json (local development)
    elif Path("token.json").exists():
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        logger.debug("Loaded credentials from token.json")

    else:
        raise RuntimeError(
            "No Gmail credentials found. "
            "Set GMAIL_TOKEN_JSON env var (Render) or run generate_token.py locally."
        )

    # 3. Refresh if expired
    if creds.expired and creds.refresh_token:
        logger.info("Refreshing expired Gmail token...")
        creds.refresh(Request())
        logger.info("Token refreshed successfully")

    return build("gmail", "v1", credentials=creds)
