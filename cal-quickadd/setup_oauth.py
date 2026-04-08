#!/usr/bin/env python3
"""One-time OAuth setup script.

Run this locally (not in Docker) to authorize Google Calendar access.
It opens a browser for Google sign-in and saves the refresh token.

Usage:
    pip install google-auth-oauthlib
    python setup_oauth.py config/credentials.json config/token.json
"""

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <credentials.json> <token.json>")
        sys.exit(1)

    creds_path = Path(sys.argv[1])
    token_path = Path(sys.argv[2])

    if not creds_path.exists():
        print(f"Error: {creds_path} not found")
        print("Download it from Google Cloud Console > APIs & Services > Credentials")
        sys.exit(1)

    token_path.parent.mkdir(parents=True, exist_ok=True)

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())

    print(f"Token saved to {token_path}")
    print("You can now start the service.")


if __name__ == "__main__":
    main()
