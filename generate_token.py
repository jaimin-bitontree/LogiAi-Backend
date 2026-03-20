from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import os
import json

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify"
]

def generate_token():
    creds = None

    # Check if token already exists
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json", SCOPES
        )

    # If no valid token — open browser
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token.json
        with open("token.json", "w") as f:
            f.write(creds.to_json())

    print("\n✅ token.json created successfully")
    print("\n" + "─" * 50)
    print("Copy below content for Render GOOGLE_TOKEN_JSON:")
    print("─" * 50)
    print(creds.to_json())
    print("─" * 50)

if __name__ == "__main__":
    generate_token()




