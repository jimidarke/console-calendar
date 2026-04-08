import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from . import config

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def get_credentials() -> Credentials:
    token_path = Path(config.GOOGLE_TOKEN_PATH)
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        log.info("Access token expired, refreshing...")
        creds.refresh(Request())
        log.info("Token refreshed successfully")
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
