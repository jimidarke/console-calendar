import json
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

_REQUIRED = ("GEMINI_API_KEY", "GOOGLE_CALENDAR_ID")
_missing = [k for k in _REQUIRED if not os.environ.get(k)]
if _missing:
    log.critical("Missing required env vars: %s — exiting", ", ".join(_missing))
    sys.exit(1)

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GOOGLE_CALENDAR_ID = os.environ["GOOGLE_CALENDAR_ID"]
GOOGLE_CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "/config/credentials.json")
GOOGLE_TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", "/config/token.json")
TIMEZONE = os.environ.get("TIMEZONE", "America/Edmonton")
FAMILY_MEMBERS = [m.strip() for m in os.environ.get("FAMILY_MEMBERS", "").split(",") if m.strip()]
FAMILY_CALENDARS: dict[str, str] = json.loads(os.environ.get("FAMILY_CALENDARS", "{}"))
