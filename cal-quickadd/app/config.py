import json
import logging
import os
import sys
from pathlib import Path

# Use the shared, stdlib-only loader from the repo root if available. If running
# from a container that doesn't ship cc_env (legacy cal-quickadd/Dockerfile), the
# .env can still come from docker-compose's env_file, so this is best-effort.
try:
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_REPO_ROOT))
    sys.path.insert(0, "/app")  # canonical Dockerfile location
    from cc_env import load_env  # noqa: E402

    load_env(Path(__file__).resolve())
except ImportError:
    pass

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

GEMINI_MODEL_PRIMARY = os.environ.get("GEMINI_MODEL_PRIMARY", "gemini-2.5-flash")
GEMINI_MODEL_FALLBACK = os.environ.get("GEMINI_MODEL_FALLBACK", "gemini-2.5-flash-lite")

# Optional shared-secret check on POST endpoints. Off by default.
CAL_TOKEN = os.environ.get("CAL_TOKEN", "").strip() or None
