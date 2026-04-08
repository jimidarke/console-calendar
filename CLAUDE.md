# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Console Calendar is an htop-like terminal UI for displaying Home Assistant calendar agenda. It uses Python's built-in curses library for the TUI with zero external dependencies.

## Running the Application

```bash
# Run the calendar console
./run_calendar.sh
# or
python3 ha_calendar_console.py

# List available calendars from Home Assistant
python3 ha_list_calendars.py

# Test API connection and configuration
python3 test_ha_calendar.py
```

## Configuration

All configuration is done via environment variables loaded from a `.env` file in the project root. Copy `.env.example` to `.env` and set values.

Required variables:
- `HOMEASSISTANT_URL` - Home Assistant server URL
- `HOMEASSISTANT_LONG_LIVE_TOKEN` - Long-lived access token from HA

Key optional variables:
- `HA_CALENDAR_ENTITY` - Calendar entity ID (default: `calendar.family`)
- `HA_CALENDAR_TITLE` - Header title
- `HA_DAYS_AHEAD` - Days to display (1-30)
- `HA_USE_UNICODE` - Unicode symbols vs ASCII fallback
- `HA_TIME_FORMAT` - 12 or 24 hour format
- `HA_DEFAULT_VIEW` - Starting view: `agenda`, `month`, or `week`
- `HA_WEEK_HOUR_START` / `HA_WEEK_HOUR_END` - Hour range for week view

## Views

Three display modes available, switchable via keyboard:

- **Agenda View** (`a`) - Default scrolling list of events by day
- **Month View** (`m`) - Calendar grid with activity indicators (● timed, ○ all-day)
- **Week View** (`w`) - 7-day planner with hourly time slots

Navigation:
- `a`/`m`/`w` - Switch views
- `←`/`→` - Navigate months/weeks (in month/week views)
- `↑`/`↓` - Scroll content
- `Home` - Reset to current period

## Architecture

**Single-file TUI application** (`ha_calendar_console.py`):
- `load_env_file()` - Loads `.env` from script directory at import time
- `HACalendarClient` - HTTP client for Home Assistant calendar API using urllib (no requests dependency)
- `parse_event_time()` / `group_events_by_date()` - Event parsing and date grouping
- `CalendarUI` - Curses-based display with color pairs, scrolling, and keyboard handling
  - `build_agenda_content()` - Vertical scrolling event list
  - `build_month_content()` - Calendar grid with activity indicators
  - `build_week_content()` - 7-column hourly planner
- Main loop: polls API at configurable interval, redraws screen every second

**Utility scripts**:
- `ha_list_calendars.py` - Lists available HA calendar entities
- `test_ha_calendar.py` - Validates API connectivity and fetches sample events
- `setup_kiosk.sh` - Configures Linux auto-login and auto-start for kiosk displays

**Data flow**: HA API → `HACalendarClient.get_events()` → cached events → `group_events_by_date()` → `CalendarUI.build_content()` → curses rendering

The application avoids external dependencies by using only Python standard library (curses, urllib, json, datetime, zoneinfo).
