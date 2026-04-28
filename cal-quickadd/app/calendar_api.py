import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from . import config

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# Tracks the last refresh outcome so /health can surface OAuth status without
# blocking on a real Google call.
last_refresh_error: str | None = None
last_refresh_success_at: float | None = None


def get_credentials() -> Credentials:
    token_path = Path(config.GOOGLE_TOKEN_PATH)
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    global last_refresh_error, last_refresh_success_at
    if creds and creds.expired and creds.refresh_token:
        log.info("Access token expired, refreshing...")
        try:
            creds.refresh(Request())
        except RefreshError as e:
            last_refresh_error = str(e)[:200]
            log.error("Token refresh failed: %s", e)
            raise
        log.info("Token refreshed successfully")
        last_refresh_error = None
        last_refresh_success_at = time.time()
        try:
            token_path.write_text(creds.to_json())
        except OSError:
            log.warning("Could not persist refreshed token to %s", token_path)
    elif not creds or not creds.valid:
        # This will only run during initial setup (needs browser)
        flow = InstalledAppFlow.from_client_secrets_file(config.GOOGLE_CREDENTIALS_PATH, SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return creds


def get_oauth_status() -> dict:
    """Return a small dict suitable for /health.

    The refresh_token's expiry is not advertised by Google. We use the token.json
    file mtime as a proxy for "when the refresh_token was last minted", and a
    user-configured TTL (`OAUTH_REFRESH_TOKEN_TTL_DAYS`, default 7 — the Testing-mode
    rule) to estimate how long it has left.

    States:
      - "missing"  : token.json absent
      - "expired"  : last refresh attempt failed with invalid_grant, or age > TTL
      - "warning"  : age >= 80% of TTL (a day or two before expiry)
      - "ok"       : age below 80% of TTL
    """
    token_path = Path(config.GOOGLE_TOKEN_PATH)
    ttl_days = int(os.environ.get("OAUTH_REFRESH_TOKEN_TTL_DAYS", "7"))
    ttl_s = ttl_days * 86400

    if not token_path.exists():
        return {
            "state": "missing",
            "token_path": str(token_path),
            "last_refresh_error": last_refresh_error,
        }

    mtime = token_path.stat().st_mtime
    age_s = max(0, int(time.time() - mtime))
    remaining_s = ttl_s - age_s

    if last_refresh_error and "invalid_grant" in last_refresh_error.lower():
        state = "expired"
    elif remaining_s <= 0:
        state = "expired"
    elif age_s >= int(ttl_s * 0.8):
        state = "warning"
    else:
        state = "ok"

    return {
        "state": state,
        "age_seconds": age_s,
        "ttl_seconds": ttl_s,
        "remaining_seconds": remaining_s,
        "minted_at": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
        "last_refresh_error": last_refresh_error,
        "last_refresh_success_at": (
            datetime.fromtimestamp(last_refresh_success_at).isoformat(timespec="seconds")
            if last_refresh_success_at
            else None
        ),
    }


def get_calendar_id(person: str | None) -> str:
    if person and person.lower() in config.FAMILY_CALENDARS:
        return config.FAMILY_CALENDARS[person.lower()]
    return config.GOOGLE_CALENDAR_ID


def create_event(
    title: str,
    date_str: str,
    start_time: str | None,
    duration_minutes: int = 60,
    person: str | None = None,
) -> dict:
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    calendar_id = get_calendar_id(person)
    tz = ZoneInfo(config.TIMEZONE)

    if start_time:
        # Timed event
        start_dt = datetime.fromisoformat(f"{date_str}T{start_time}").replace(tzinfo=tz)
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        event_body = {
            "summary": title,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": config.TIMEZONE},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": config.TIMEZONE},
        }
    else:
        # All-day event
        event_body = {
            "summary": title,
            "start": {"date": date_str},
            "end": {"date": date_str},
        }

    if person:
        event_body["description"] = f"Added for: {person}"

    event = service.events().insert(calendarId=calendar_id, body=event_body).execute()

    log.info("Created event: %s (%s)", event.get("htmlLink"), title)

    return {
        "id": event["id"],
        "title": title,
        "link": event.get("htmlLink", ""),
        "start": event["start"],
        "end": event["end"],
    }
