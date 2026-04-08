import base64
import json
import logging
from datetime import date

import google.generativeai as genai

from . import config

log = logging.getLogger(__name__)

genai.configure(api_key=config.GEMINI_API_KEY)

SYSTEM_PROMPT = """\
You are a calendar event parser. Extract structured event data from casual, messy human input.

Today's date: {today} ({day_name})
Timezone: {timezone}
Known family members and nicknames:
- jimi (dad/husband)
- tricia (mom/wife)
- nic / nicolas
- soph / sophia
- jonnie / jonathan
- dad / steve (grandpa)

Rules:
- Resolve relative dates ("thursday" = next Thursday including today, "tomorrow", "next week")
- Parse casual times: "445pm" = 16:45, "3" in afternoon context = 15:00, "noon" = 12:00
- If no time is given, set start_time to null (will become all-day event)
- If no date is given, assume today if a future time, otherwise tomorrow
- Default duration: 60 minutes
- If a known family member name or nickname appears, set "person" to their primary name (nic, soph, jonnie, jimi, tricia, dad)
- If input is too vague or nonsensical to parse, set confidence to "unparseable"

Respond with ONLY valid JSON matching this schema:
{{
  "title": "string - event title, cleaned up but preserving intent",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM (24h) or null for all-day",
  "duration_minutes": 60,
  "person": "family member name or null",
  "confidence": "high | low | unparseable"
}}
"""

IMAGE_PROMPT = """\
You are a calendar event extractor. Look at this image (could be a permission slip, school flyer, \
handwritten note, text message screenshot, or email) and extract ALL calendar events you can find.

Today's date: {today} ({day_name})
Timezone: {timezone}
Known family members: jimi, tricia, nic, soph, jonnie, dad (steve)

For each event found, extract:
- title: event name
- date: YYYY-MM-DD (resolve relative dates based on today)
- start_time: HH:MM (24h) or null if no time specified
- duration_minutes: best guess, default 60
- person: family member name if identifiable, else null
- confidence: high | low

Respond with ONLY a valid JSON array of events. If no events found, return an empty array [].
Example: [{{"title": "PTA Meeting", "date": "2026-04-15", "start_time": "18:30", "duration_minutes": 90, "person": "jonnie", "confidence": "high"}}]
"""


def build_prompt(today: date) -> str:
    members = ", ".join(config.FAMILY_MEMBERS) if config.FAMILY_MEMBERS else "none configured"
    return SYSTEM_PROMPT.format(
        today=today.isoformat(),
        day_name=today.strftime("%A"),
        timezone=config.TIMEZONE,
        members=members,
    )


def build_image_prompt(today: date) -> str:
    return IMAGE_PROMPT.format(
        today=today.isoformat(),
        day_name=today.strftime("%A"),
        timezone=config.TIMEZONE,
    )


async def parse(text: str) -> dict:
    today = date.today()
    system = build_prompt(today)

    model = genai.GenerativeModel("gemini-2.0-flash", system_instruction=system)

    response = model.generate_content(
        text,
        generation_config=genai.GenerationConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
        request_options={"timeout": 30},
    )

    raw = response.text.strip()
    log.info("Gemini response: %s", raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.error("Gemini returned invalid JSON: %s", raw[:500])
        raise ValueError("AI returned unparseable response")

    for field in ("title", "date", "confidence"):
        if field not in parsed:
            log.error("Missing field '%s' in Gemini response: %s", field, raw[:500])
            raise ValueError(f"Missing required field: {field}")

    return parsed


async def parse_image(image_bytes: bytes, mime_type: str) -> list[dict]:
    today = date.today()
    prompt = build_image_prompt(today)

    model = genai.GenerativeModel("gemini-2.0-flash")

    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = model.generate_content(
        [
            {"mime_type": mime_type, "data": b64},
            prompt,
        ],
        generation_config=genai.GenerationConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
        request_options={"timeout": 30},
    )

    raw = response.text.strip()
    log.info("Gemini image response: %s", raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.error("Gemini returned invalid JSON for image: %s", raw[:500])
        raise ValueError("AI returned unparseable response for image")

    # Ensure it's a list
    if isinstance(parsed, dict):
        parsed = [parsed]

    return parsed
