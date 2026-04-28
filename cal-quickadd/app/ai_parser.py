import asyncio
import base64
import json
import logging
import random
from datetime import date

import google.generativeai as genai

from . import config

log = logging.getLogger(__name__)

genai.configure(api_key=config.GEMINI_API_KEY)


class QuotaExceeded(Exception):
    """Gemini daily/per-minute quota exhausted; both primary and fallback models unavailable."""

    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


# Tracks the last quota state seen by the parser so /health can surface it.
quota_state: str = "ok"  # "ok" | "throttled" | "exhausted"
last_error: str | None = None


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


def _is_quota_error(exc: BaseException) -> bool:
    """Heuristic: google-generativeai raises ResourceExhausted or includes '429' in str."""
    name = type(exc).__name__
    if name in ("ResourceExhausted", "TooManyRequests"):
        return True
    s = str(exc)
    return "429" in s or "Resource exhausted" in s or "quota" in s.lower()


async def _call_gemini(*, system: str | None, parts, model_override: str | None = None) -> str:
    """Call Gemini with retry on transient 429s and fallback to a secondary model on hard quota.

    parts: either a string (text prompt) or a list of content parts for multimodal calls.
    Returns response.text.
    """
    global quota_state, last_error

    primary = model_override or config.GEMINI_MODEL_PRIMARY
    fallback = config.GEMINI_MODEL_FALLBACK if not model_override else None
    gen_cfg = genai.GenerationConfig(temperature=0, response_mime_type="application/json")

    async def attempt(model_name: str) -> str:
        model = genai.GenerativeModel(model_name, system_instruction=system) if system else genai.GenerativeModel(model_name)
        # google-generativeai is sync; run in a worker thread so we don't block the event loop.
        return await asyncio.to_thread(
            lambda: model.generate_content(
                parts,
                generation_config=gen_cfg,
                request_options={"timeout": 30},
            ).text
        )

    delay = 2.0
    last_exc: Exception | None = None
    for i in range(3):
        try:
            text = await attempt(primary)
            if quota_state != "ok":
                log.info("Gemini quota recovered (model=%s)", primary)
            quota_state = "ok"
            last_error = None
            return text
        except Exception as e:
            last_exc = e
            if not _is_quota_error(e):
                raise
            log.warning("Gemini 429 on %s (attempt %d/3): %s", primary, i + 1, e)
            quota_state = "throttled"
            last_error = str(e)[:200]
            if i < 2:
                await asyncio.sleep(delay + random.uniform(0, 1))
                delay *= 2

    # Primary exhausted — try fallback once.
    if fallback and fallback != primary:
        log.warning("Primary model %s exhausted, falling back to %s", primary, fallback)
        try:
            text = await attempt(fallback)
            quota_state = "throttled"  # primary still down
            last_error = f"primary {primary} exhausted, using fallback {fallback}"
            return text
        except Exception as e:
            last_exc = e
            if not _is_quota_error(e):
                raise
            log.error("Fallback model %s also exhausted: %s", fallback, e)

    quota_state = "exhausted"
    last_error = str(last_exc)[:200] if last_exc else "quota exhausted"
    raise QuotaExceeded(f"Gemini quota exhausted: {last_exc}", retry_after=60)


async def parse(text: str) -> dict:
    today = date.today()
    system = build_prompt(today)

    raw = (await _call_gemini(system=system, parts=text)).strip()
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

    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    parts = [{"mime_type": mime_type, "data": b64}, prompt]

    raw = (await _call_gemini(system=None, parts=parts)).strip()
    log.info("Gemini image response: %s", raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.error("Gemini returned invalid JSON for image: %s", raw[:500])
        raise ValueError("AI returned unparseable response for image")

    if isinstance(parsed, dict):
        parsed = [parsed]

    return parsed
