# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Console Calendar is two related but independent components:

1. **Console TUI** (`ha_calendar_console.py`) — A curses-based terminal UI that displays a Home Assistant calendar agenda. Zero external dependencies (stdlib only). Designed for kiosk/Raspberry Pi use.

2. **cal-quickadd** (`cal-quickadd/`) — A FastAPI web service that parses natural language (and images) into Google Calendar events using Gemini AI. Separate dependency stack, runs in Docker.

These share a repo but have no code dependencies on each other.

## Commands

### Console TUI
```bash
./run_calendar.sh                          # Launch via wrapper
python3 ha_calendar_console.py             # Launch directly
python3 ha_list_calendars.py               # List available HA calendars
python3 test_ha_calendar.py                # Test API connectivity
sudo ./setup_kiosk.sh check|install|uninstall  # Kiosk mode
```

### cal-quickadd
```bash
cd cal-quickadd
pip install -r requirements.txt
python setup_oauth.py                      # Initial Google OAuth setup
uvicorn app.main:app --host 0.0.0.0 --port 8000  # Run server
docker compose up                          # Or via Docker
python test_parser.py                      # Test AI parsing
python test_api.py                         # Test API endpoints
```

## Architecture

### Console TUI (`ha_calendar_console.py` — single file)
- `HACalendarClient` — HA REST API client (`/api/calendars/{entity}`), Bearer token auth, cached with configurable refresh
- `CalendarUI` — curses rendering with three views:
  - `build_agenda_content()` — scrolling event list by day
  - `build_month_content()` — calendar grid with event indicators
  - `build_week_content()` — 7-column hourly planner
- `parse_event_time()` / `group_events_by_date()` — event data processing
- Config loaded from `.env` via `load_env_file()` at import time
- Entry: `run()` → `curses.wrapper(main)`

### cal-quickadd
- `app/main.py` — FastAPI app with `/add` (text→event) and `/scan` (image→events) endpoints, rate limiting middleware
- `app/ai_parser.py` — Gemini 2.0 Flash for NLP parsing. Structured prompts with family member context and date awareness
- `app/calendar_api.py` — Google Calendar API via OAuth2. Per-family-member calendar routing via `FAMILY_CALENDARS` env var
- `app/config.py` — env var loading. Requires `GEMINI_API_KEY` and `GOOGLE_CALENDAR_ID`

## Configuration

Both components use `.env` files (git-ignored). The console TUI reads `HOMEASSISTANT_URL`, `HOMEASSISTANT_LONG_LIVE_TOKEN`, and `HA_*` vars. cal-quickadd requires `GEMINI_API_KEY`, `GOOGLE_CALENDAR_ID`, and Google OAuth credentials at `/config/`.
