import logging
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai_parser, calendar_api, config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="cal-quickadd", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Track last event for health endpoint
_last_event: dict | None = None

# Rate limiting: track request timestamps per IP
_rate_limit: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX = 30
RATE_LIMIT_WINDOW = 60  # seconds

STATIC_DIR = Path(__file__).parent / "static"


# --- Middleware: IP logging + rate limiting ---

@app.middleware("http")
async def log_and_rate_limit(request: Request, call_next):
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    ua = request.headers.get("user-agent", "unknown")
    log.info("%s %s [ip=%s ua=%s]", request.method, request.url.path, client_ip, ua[:80])

    # Rate limit POST endpoints only
    if request.method == "POST":
        now = time.time()
        timestamps = _rate_limit[client_ip]
        # Clean old entries
        _rate_limit[client_ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
        if len(_rate_limit[client_ip]) >= RATE_LIMIT_MAX:
            log.warning("Rate limit hit: ip=%s", client_ip)
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Try again in a minute."})
        _rate_limit[client_ip].append(now)

    return await call_next(request)


# --- Models ---

class AddRequest(BaseModel):
    text: str
    source: str = "web"


class AddResponse(BaseModel):
    status: str
    event: dict | None = None
    parsed: dict | None = None
    message: str


# --- Routes ---

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/add", response_model=AddResponse)
async def add_event(req: AddRequest):
    global _last_event

    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        parsed = await ai_parser.parse(req.text)
    except Exception as e:
        log.error("Parse failed: %s", e)
        raise HTTPException(status_code=422, detail=f"Could not parse input: {e}")

    if parsed.get("confidence") == "unparseable":
        return AddResponse(
            status="unparseable",
            parsed=parsed,
            message=f"Could not understand: '{req.text}'. Try something like 'dentist friday 2pm'.",
        )

    if parsed.get("confidence") == "low":
        return AddResponse(
            status="needs_confirmation",
            parsed=parsed,
            message=f"Parsed as: {parsed['title']} on {parsed['date']}"
            + (f" at {parsed['start_time']}" if parsed.get("start_time") else " (all day)")
            + ". Send again with confirmation to create.",
        )

    try:
        event = calendar_api.create_event(
            title=parsed["title"],
            date_str=parsed["date"],
            start_time=parsed.get("start_time"),
            duration_minutes=parsed.get("duration_minutes", 60),
            person=parsed.get("person"),
        )
    except Exception as e:
        log.error("Calendar API failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Failed to create calendar event: {e}")

    _last_event = {"event": event, "source": req.source, "created_at": datetime.now().isoformat()}

    time_str = parsed["start_time"] if parsed.get("start_time") else "all day"
    person_str = f" ({parsed['person']})" if parsed.get("person") else ""
    message = f"Added: {parsed['title']} on {parsed['date']} at {time_str}{person_str}"

    log.info("Event created: %s [source=%s]", message, req.source)

    return AddResponse(status="created", event=event, parsed=parsed, message=message)


@app.post("/scan")
async def scan_image(file: UploadFile = File(...)):
    global _last_event

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload must be an image (JPEG, PNG, etc.)")

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 10 MB)")

    try:
        events = await ai_parser.parse_image(image_bytes, file.content_type)
    except Exception as e:
        log.error("Image parse failed: %s", e)
        raise HTTPException(status_code=422, detail=f"Could not extract events from image: {e}")

    if not events:
        return {"status": "no_events", "events": [], "message": "No calendar events found in this image."}

    # Create all high-confidence events, return low-confidence for confirmation
    created = []
    needs_confirmation = []

    for ev in events:
        if ev.get("confidence") == "high":
            try:
                cal_event = calendar_api.create_event(
                    title=ev["title"],
                    date_str=ev["date"],
                    start_time=ev.get("start_time"),
                    duration_minutes=ev.get("duration_minutes", 60),
                    person=ev.get("person"),
                )
                created.append({**ev, "calendar_event": cal_event})
                _last_event = {"event": cal_event, "source": "scan", "created_at": datetime.now().isoformat()}
            except Exception as e:
                log.error("Calendar create failed for scanned event: %s", e)
                ev["error"] = str(e)
                needs_confirmation.append(ev)
        else:
            needs_confirmation.append(ev)

    parts = []
    if created:
        parts.append(f"Created {len(created)} event(s)")
    if needs_confirmation:
        parts.append(f"{len(needs_confirmation)} need confirmation")

    return {
        "status": "ok",
        "created": created,
        "needs_confirmation": needs_confirmation,
        "message": ". ".join(parts) + ".",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timezone": config.TIMEZONE,
        "family_members": config.FAMILY_MEMBERS,
        "last_event": _last_event,
    }


# Mount static files last (so explicit routes take priority)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
