#!/usr/bin/env python3
"""
Console Calendar - Home Assistant Calendar Display
An htop-like terminal UI for displaying family calendar agenda.

Usage:
    ./ha_calendar_console.py

Environment Variables:
    See .env.example for full list of configuration options.

Controls:
    q, ESC        - Quit
    a             - Agenda view (list)
    m             - Month view (grid)
    w             - Week view (columns)
    UP/DOWN, j/k  - Scroll
    LEFT/RIGHT    - Navigate months/weeks (in month/week views)
    PgUp/PgDn     - Scroll page
    Home/End      - Jump to top/bottom, reset to current period
    r             - Force refresh
    F2            - Quick add event (requires CAL_QUICKADD_URL)

Repository: https://github.com/jimidarke/console-calendar
"""

import curses
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python < 3.9 fallback
    ZoneInfo = None

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration (loaded from environment variables)
# ═══════════════════════════════════════════════════════════════════════════════

def load_env_file():
    """Load .env file from script directory if it exists."""
    script_dir = Path(__file__).parent
    env_file = script_dir / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip()
                    # Don't override existing env vars
                    if key not in os.environ:
                        os.environ[key] = value

# Load .env on import
load_env_file()

# Home Assistant Connection
HA_URL = os.environ.get("HOMEASSISTANT_URL", "http://192.168.1.40:8123")
HA_TOKEN = os.environ.get("HOMEASSISTANT_LONG_LIVE_TOKEN", "")

# Calendar Settings
CALENDAR_ENTITY = os.environ.get("HA_CALENDAR_ENTITY", "calendar.family")
CALENDAR_TITLE = os.environ.get("HA_CALENDAR_TITLE", "FAMILY CALENDAR")
DAYS_AHEAD = int(os.environ.get("HA_DAYS_AHEAD", "60"))

# Display Options
USE_UNICODE = os.environ.get("HA_USE_UNICODE", "true").lower() == "true"
TIME_FORMAT = os.environ.get("HA_TIME_FORMAT", "12")
SHOW_LOCATIONS = os.environ.get("HA_SHOW_LOCATIONS", "true").lower() == "true"
SHOW_DESCRIPTIONS = os.environ.get("HA_SHOW_DESCRIPTIONS", "false").lower() == "true"
TIMEZONE_NAME = os.environ.get("HA_TIMEZONE", "")

# Refresh Intervals
API_REFRESH_INTERVAL = int(os.environ.get("HA_API_REFRESH_INTERVAL", "60"))
SCREEN_REFRESH_INTERVAL = int(os.environ.get("HA_SCREEN_REFRESH_INTERVAL", "1"))

# View Settings
DEFAULT_VIEW = os.environ.get("HA_DEFAULT_VIEW", "agenda")  # agenda, month, week
WEEK_START = os.environ.get("HA_WEEK_START", "monday").lower()  # monday or sunday
WEEK_HOUR_START = int(os.environ.get("HA_WEEK_HOUR_START", "7"))
WEEK_HOUR_END = int(os.environ.get("HA_WEEK_HOUR_END", "21"))

# Quick Add Integration
CAL_QUICKADD_URL = os.environ.get("CAL_QUICKADD_URL", "")


def get_local_tz():
    """Get the configured timezone or system local."""
    if TIMEZONE_NAME and ZoneInfo:
        try:
            return ZoneInfo(TIMEZONE_NAME)
        except Exception:
            pass
    return None


def now_local() -> datetime:
    """Get current time in configured timezone."""
    tz = get_local_tz()
    if tz:
        return datetime.now(tz)
    return datetime.now()


def today_local():
    """Get today's date in configured timezone."""
    return now_local().date()

# ═══════════════════════════════════════════════════════════════════════════════
# ASCII Art & Symbols
# ═══════════════════════════════════════════════════════════════════════════════

LOGO = r"""
  ╔═══════════════════════════════════════════════════════════════════╗
  ║  ▄▀▀▀▀▄   ▄▀▀▀▀▄   ▄▀▀▀▀▄   ▄▀▀▀▀▄   ▄▀▀▀▀▄   ▄▀▀▀▀▄   ▄▀▀▀▀▄    ║
  ║  █    █   █    █   █    █   █    █   █    █   █    █   █    █    ║
  ║  ▀▄▄▄▄▀   ▀▄▄▄▄▀   ▀▄▄▄▄▀   ▀▄▄▄▄▀   ▀▄▄▄▄▀   ▀▄▄▄▄▀   ▀▄▄▄▄▀    ║
  ╚═══════════════════════════════════════════════════════════════════╝
"""

BOX_CHARS = {
    'tl': '╔', 'tr': '╗', 'bl': '╚', 'br': '╝',
    'h': '═', 'v': '║',
    'lt': '╠', 'rt': '╣', 'tt': '╦', 'bt': '╩', 'x': '╬'
}

SYMBOLS = {
    'calendar': '📅',
    'clock': '⏰',
    'sun': '☀',
    'moon': '☾',
    'star': '★',
    'arrow': '►',
    'dot': '●',
    'diamond': '◆',
    'check': '✓',
    'allday': '▓',
    'timed': '●',
    'allday_icon': '○',
    'today': '◉',
    'continuation': '│',
}

# Fallback ASCII symbols for terminals without Unicode
SYMBOLS_ASCII = {
    'calendar': '[C]',
    'clock': '[T]',
    'sun': '*',
    'moon': 'D',
    'star': '*',
    'arrow': '>',
    'dot': 'o',
    'diamond': '<>',
    'check': '+',
    'allday': '#',
    'timed': '*',
    'allday_icon': 'o',
    'today': '@',
    'continuation': '|',
}


# ═══════════════════════════════════════════════════════════════════════════════
# Home Assistant API Client
# ═══════════════════════════════════════════════════════════════════════════════

class HACalendarClient:
    """Simple Home Assistant API client for calendar data."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.last_fetch = 0
        self.cached_events = []
        self.last_error = None

    def _make_request(self, endpoint: str) -> Optional[dict]:
        """Make authenticated request to HA API."""
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            self.last_error = f"HTTP {e.code}: {e.reason}"
            return None
        except urllib.error.URLError as e:
            self.last_error = f"Connection error: {e.reason}"
            return None
        except json.JSONDecodeError as e:
            self.last_error = f"JSON parse error: {e}"
            return None
        except Exception as e:
            self.last_error = f"Error: {e}"
            return None

    def list_calendars(self) -> list:
        """List available calendar entities."""
        result = self._make_request("/api/calendars")
        return result if result else []

    def get_events(self, entity_id: str, days_ahead: int = 7) -> list:
        """Fetch calendar events for the next N days."""
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=days_ahead + 1)

        start_str = start.strftime("%Y-%m-%dT%H:%M:%S")
        end_str = end.strftime("%Y-%m-%dT%H:%M:%S")

        endpoint = f"/api/calendars/{entity_id}?start={start_str}&end={end_str}"
        result = self._make_request(endpoint)

        if result is not None:
            self.cached_events = result
            self.last_fetch = time.time()
            self.last_error = None

        return self.cached_events

    def should_refresh(self) -> bool:
        """Check if we should fetch new data."""
        return (time.time() - self.last_fetch) >= API_REFRESH_INTERVAL


# ═══════════════════════════════════════════════════════════════════════════════
# Event Processing
# ═══════════════════════════════════════════════════════════════════════════════

def parse_event_time(event: dict) -> tuple[datetime, datetime, bool]:
    """Parse event start/end times. Returns (start, end, is_all_day)."""
    start = event.get('start', {})
    end = event.get('end', {})

    if 'date' in start:
        # All-day event
        start_dt = datetime.strptime(start['date'], "%Y-%m-%d")
        end_dt = datetime.strptime(end['date'], "%Y-%m-%d") if 'date' in end else start_dt + timedelta(days=1)
        return start_dt, end_dt, True
    else:
        # Timed event
        start_str = start.get('dateTime', '')
        end_str = end.get('dateTime', '')

        # Handle timezone offset in ISO format
        for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
            try:
                start_dt = datetime.strptime(start_str.replace(':', '').replace('-', '', 2),
                                            fmt.replace(':', '').replace('-', '', 2) if '%z' in fmt else fmt)
                break
            except ValueError:
                continue
        else:
            # Fallback: try basic parsing
            start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))

        for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
            try:
                end_dt = datetime.strptime(end_str.replace(':', '').replace('-', '', 2),
                                          fmt.replace(':', '').replace('-', '', 2) if '%z' in fmt else fmt)
                break
            except ValueError:
                continue
        else:
            end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))

        # Convert to local naive datetime for display
        if start_dt.tzinfo:
            start_dt = start_dt.replace(tzinfo=None)
        if end_dt.tzinfo:
            end_dt = end_dt.replace(tzinfo=None)

        return start_dt, end_dt, False


def group_events_by_date(events: list) -> dict[str, list]:
    """Group events by date, sorted by time."""
    grouped = {}

    for event in events:
        try:
            start_dt, end_dt, is_all_day = parse_event_time(event)
        except Exception:
            continue

        date_key = start_dt.strftime("%Y-%m-%d")

        if date_key not in grouped:
            grouped[date_key] = []

        grouped[date_key].append({
            'summary': event.get('summary', 'Untitled'),
            'start': start_dt,
            'end': end_dt,
            'is_all_day': is_all_day,
            'description': event.get('description', ''),
            'location': event.get('location', ''),
        })

    # Sort events within each day
    for date_key in grouped:
        grouped[date_key].sort(key=lambda e: (not e['is_all_day'], e['start']))

    return grouped


# ═══════════════════════════════════════════════════════════════════════════════
# Terminal UI Rendering
# ═══════════════════════════════════════════════════════════════════════════════

class CalendarUI:
    """Curses-based calendar display."""

    # Color pair indices
    COLOR_HEADER = 1
    COLOR_DATE = 2
    COLOR_TIME = 3
    COLOR_ALLDAY = 4
    COLOR_EVENT = 5
    COLOR_ERROR = 6
    COLOR_DIM = 7
    COLOR_ACCENT = 8

    def __init__(self, stdscr, client: HACalendarClient, calendar_entity: str, title: str = "FAMILY CALENDAR"):
        self.stdscr = stdscr
        self.client = client
        self.calendar_entity = calendar_entity
        self.title = title
        self.scroll_offset = 0
        self.content_lines = []
        self.use_unicode = USE_UNICODE
        self.show_locations = SHOW_LOCATIONS
        self.show_descriptions = SHOW_DESCRIPTIONS
        self.running = True

        # View state
        self.current_view = DEFAULT_VIEW  # 'agenda', 'month', 'week'
        self.view_offset = 0  # Offset for month/week navigation (0 = current)
        self.cached_events = []  # Store events for all views

        # Quick add modal state
        self.modal_state = None        # None | "input" | "sending" | "result"
        self.input_buffer = ""
        self.input_cursor = 0
        self.quickadd_result = None
        self.quickadd_thread = None

        self._init_colors()
        self._init_screen()

    def _init_colors(self):
        """Initialize color pairs."""
        curses.start_color()
        curses.use_default_colors()

        try:
            curses.init_pair(self.COLOR_HEADER, curses.COLOR_CYAN, -1)
            curses.init_pair(self.COLOR_DATE, curses.COLOR_YELLOW, -1)
            curses.init_pair(self.COLOR_TIME, curses.COLOR_GREEN, -1)
            curses.init_pair(self.COLOR_ALLDAY, curses.COLOR_MAGENTA, -1)
            curses.init_pair(self.COLOR_EVENT, curses.COLOR_WHITE, -1)
            curses.init_pair(self.COLOR_ERROR, curses.COLOR_RED, -1)
            curses.init_pair(self.COLOR_DIM, curses.COLOR_BLACK, -1)
            curses.init_pair(self.COLOR_ACCENT, curses.COLOR_BLUE, -1)
        except curses.error:
            pass  # Colors not supported

    def _init_screen(self):
        """Initialize screen settings."""
        curses.curs_set(0)  # Hide cursor
        self.stdscr.nodelay(True)  # Non-blocking input
        self.stdscr.timeout(100)  # 100ms input timeout

        # Test Unicode support
        try:
            self.stdscr.addstr(0, 0, "═")
            self.stdscr.clear()
        except curses.error:
            self.use_unicode = False

    def get_symbol(self, name: str) -> str:
        """Get symbol with fallback to ASCII."""
        if self.use_unicode:
            return SYMBOLS.get(name, '?')
        return SYMBOLS_ASCII.get(name, '?')

    def build_content(self, events: list) -> list[tuple[str, int]]:
        """Build content lines based on current view."""
        if self.current_view == 'month':
            return self.build_month_content(events)
        elif self.current_view == 'week':
            return self.build_week_content(events)
        else:
            return self.build_agenda_content(events)

    def build_agenda_content(self, events: list) -> list[tuple[str, int]]:
        """Build agenda view content lines with color attributes."""
        lines = []
        today = today_local()
        grouped = group_events_by_date(events)

        # Get terminal width for dynamic sizing
        _, term_width = self.stdscr.getmaxyx()
        separator_width = term_width - 6

        # Generate dates for next DAYS_AHEAD days
        for day_offset in range(DAYS_AHEAD):
            current_date = today + timedelta(days=day_offset)
            date_key = current_date.strftime("%Y-%m-%d")

            # Day label - simplified
            if day_offset == 0:
                day_label = "TODAY"
                date_suffix = current_date.strftime(" - %B %d").upper()
            elif day_offset == 1:
                day_label = "TOMORROW"
                date_suffix = current_date.strftime(" - %B %d").upper()
            else:
                day_label = current_date.strftime("%A").upper()
                date_suffix = current_date.strftime(" - %B %d").upper()

            # Special highlight border for today
            lines.append(("", 0))
            if day_offset == 0:
                # Today gets a bold double-line border
                top_border = f"  ╔{'═' * separator_width}╗"
                lines.append((top_border, curses.color_pair(self.COLOR_HEADER) | curses.A_BOLD))
                lines.append((f"  ║ {self.get_symbol('star')} {day_label}{date_suffix}{' ' * (separator_width - len(day_label) - len(date_suffix) - 3)}║",
                             curses.color_pair(self.COLOR_HEADER) | curses.A_BOLD))
                bot_border = f"  ╚{'═' * separator_width}╝"
                lines.append((bot_border, curses.color_pair(self.COLOR_HEADER) | curses.A_BOLD))
            else:
                # Other days get a simple line
                sep_line = f"  ─{'─' * separator_width}─"
                lines.append((sep_line, curses.color_pair(self.COLOR_DIM)))
                lines.append((f"    {day_label}{date_suffix}",
                             curses.color_pair(self.COLOR_DATE) | curses.A_BOLD))

            # Events for this day
            day_events = grouped.get(date_key, [])

            if not day_events:
                lines.append((f"   {self.get_symbol('dot')} No events scheduled",
                             curses.color_pair(self.COLOR_DIM)))
            else:
                for event in day_events:
                    if event['is_all_day']:
                        # All-day event
                        time_str = f"[{self.get_symbol('allday')} ALL DAY]"
                        lines.append((f"   {time_str:16} {event['summary']}",
                                     curses.color_pair(self.COLOR_ALLDAY) | curses.A_BOLD))
                    else:
                        # Timed event
                        time_str = event['start'].strftime("%I:%M %p").lstrip('0')
                        end_str = event['end'].strftime("%I:%M %p").lstrip('0')
                        lines.append((f"   {time_str:>8}        {self.get_symbol('arrow')} {event['summary']}",
                                     curses.color_pair(self.COLOR_TIME)))

                    # Show location if present and enabled
                    if self.show_locations and event.get('location'):
                        lines.append((f"                      @ {event['location'][:40]}",
                                     curses.color_pair(self.COLOR_DIM)))

                    # Show description if present and enabled
                    if self.show_descriptions and event.get('description'):
                        desc = event['description'][:60].replace('\n', ' ')
                        lines.append((f"                      {desc}",
                                     curses.color_pair(self.COLOR_DIM)))

        return lines

    def build_month_content(self, events: list) -> list[tuple[str, int]]:
        """Build month grid view content."""
        import calendar
        lines = []
        today = today_local()
        grouped = group_events_by_date(events)

        # Get terminal dimensions for dynamic sizing
        term_height, term_width = self.stdscr.getmaxyx()

        # Calculate the displayed month based on view_offset
        year = today.year
        month = today.month + self.view_offset
        while month > 12:
            month -= 12
            year += 1
        while month < 1:
            month += 12
            year -= 1

        # Get first day of month and number of days
        first_weekday, num_days = calendar.monthrange(year, month)
        month_name = calendar.month_name[month].upper()

        # Calculate number of weeks needed
        total_days = first_weekday + num_days
        num_weeks = (total_days + 6) // 7

        # Dynamic sizing
        available_width = term_width - 4
        day_width = max(8, available_width // 7)

        # Calculate rows per week based on available height
        # Reserve: header+controls(5) + month header(3) + week headers(1) + top border(1) + separators(num_weeks-1) + bottom border(1) + legend(2)
        fixed_rows = 5 + 3 + 1 + 1 + (num_weeks - 1) + 1 + 2
        available_height = term_height - fixed_rows
        rows_per_week = max(2, available_height // num_weeks)  # Minimum 2 rows per week

        # Header
        lines.append(("", 0))
        lines.append((f"  {month_name} {year}", curses.color_pair(self.COLOR_DATE) | curses.A_BOLD))
        lines.append(("", 0))

        # Week day headers
        headers = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        header_line = "  " + "".join(f"{h:^{day_width}}" for h in headers)
        lines.append((header_line, curses.color_pair(self.COLOR_HEADER) | curses.A_BOLD))

        # Top border
        border_line = "  ┌" + "┬".join(["─" * (day_width - 1)] * 7) + "┐"
        lines.append((border_line, curses.color_pair(self.COLOR_DIM)))

        # Generate weeks
        day = 1
        for week in range(6):
            if day > num_days:
                break

            # Build cell data for this week
            week_cells = []
            for weekday in range(7):
                if week == 0 and weekday < first_weekday:
                    week_cells.append(None)
                elif day > num_days:
                    week_cells.append(None)
                else:
                    current_date = datetime(year, month, day).date()
                    date_key = current_date.strftime("%Y-%m-%d")
                    day_events = grouped.get(date_key, [])
                    is_today = current_date == today
                    week_cells.append({
                        'day': day,
                        'is_today': is_today,
                        'events': day_events
                    })
                    day += 1

            # Render multiple rows per week
            for row_idx in range(rows_per_week):
                # Build row with individual cell rendering for today highlight
                row_parts = []
                row_parts.append(("  │", curses.color_pair(self.COLOR_DIM)))

                for cell in week_cells:
                    if cell is None:
                        row_parts.append((" " * (day_width - 1) + "│", curses.color_pair(self.COLOR_DIM)))
                    else:
                        cell_content = ""
                        if row_idx == 0:
                            # First row: day number
                            if cell['is_today']:
                                cell_content = f"★ {cell['day']:2d} ★"
                            else:
                                cell_content = f" {cell['day']:2d} "
                        else:
                            # Subsequent rows: show events
                            event_idx = row_idx - 1
                            if event_idx < len(cell['events']):
                                event = cell['events'][event_idx]
                                max_len = day_width - 3
                                if event['is_all_day']:
                                    title = event['summary'][:max_len - 2]
                                    cell_content = f"{self.get_symbol('allday_icon')} {title}"
                                else:
                                    # Show time + title for timed events
                                    if TIME_FORMAT == "12":
                                        time_str = event['start'].strftime("%I:%M%p").lstrip('0').replace('AM','a').replace('PM','p')
                                    else:
                                        time_str = event['start'].strftime("%H:%M")
                                    remaining = max_len - len(time_str) - 1
                                    title = event['summary'][:max(0, remaining)]
                                    cell_content = f"{time_str} {title}"
                            elif event_idx == len(cell['events']) and len(cell['events']) > 0:
                                # Empty row after events
                                cell_content = ""

                        formatted_cell = f"{cell_content:^{day_width - 1}}"[:day_width - 1] + "│"

                        # Today gets special highlight
                        if cell['is_today']:
                            row_parts.append((formatted_cell, curses.color_pair(self.COLOR_HEADER) | curses.A_BOLD))
                        elif row_idx == 0:
                            row_parts.append((formatted_cell, curses.color_pair(self.COLOR_EVENT)))
                        else:
                            row_parts.append((formatted_cell, curses.color_pair(self.COLOR_TIME)))

                # Combine parts into single line for simple rendering
                # For today highlighting, we need to render cell by cell
                full_line = "".join(part[0] for part in row_parts)

                # Check if any cell is today to use highlight
                has_today = any(cell and cell['is_today'] for cell in week_cells)
                if has_today and row_idx == 0:
                    lines.append((full_line, curses.color_pair(self.COLOR_HEADER) | curses.A_BOLD))
                elif row_idx == 0:
                    lines.append((full_line, curses.color_pair(self.COLOR_EVENT)))
                else:
                    lines.append((full_line, curses.color_pair(self.COLOR_TIME)))

            # Row separator (except after last week)
            if day <= num_days:
                sep_line = "  ├" + "┼".join(["─" * (day_width - 1)] * 7) + "┤"
                lines.append((sep_line, curses.color_pair(self.COLOR_DIM)))

        # Bottom border
        bottom_line = "  └" + "┴".join(["─" * (day_width - 1)] * 7) + "┘"
        lines.append((bottom_line, curses.color_pair(self.COLOR_DIM)))

        # Legend
        lines.append(("", 0))
        lines.append((f"  {self.get_symbol('timed')} = timed event  {self.get_symbol('allday_icon')} = all-day event  [ ] = today",
                     curses.color_pair(self.COLOR_DIM)))

        return lines

    def build_week_content(self, events: list) -> list[tuple[str, int]]:
        """Build week column view with hourly time slots."""
        lines = []
        today = today_local()
        grouped = group_events_by_date(events)

        # Get terminal dimensions for dynamic sizing
        term_height, term_width = self.stdscr.getmaxyx()

        # Calculate the week to display based on view_offset
        # Find Monday of current week
        days_since_monday = today.weekday()  # Monday = 0
        week_start = today - timedelta(days=days_since_monday) + timedelta(weeks=self.view_offset)

        # Dynamic column width calculation
        time_col_width = 6  # "12 PM" etc
        available_width = term_width - time_col_width - 2
        day_col_width = max(10, available_width // 7)

        # Calculate rows per hour based on available height
        # Reserve: header+controls(5) + week header(3) + day headers(1) + separator(1) + allday(1) + separator(1)
        num_hours = WEEK_HOUR_END - WEEK_HOUR_START
        fixed_rows = 5 + 3 + 1 + 1 + 1 + 1
        available_height = term_height - fixed_rows
        rows_per_hour = max(1, available_height // num_hours)

        # Week header
        week_end = week_start + timedelta(days=6)
        week_header = f"  WEEK OF {week_start.strftime('%b %d').upper()} - {week_end.strftime('%b %d, %Y').upper()}"
        lines.append(("", 0))
        lines.append((week_header, curses.color_pair(self.COLOR_DATE) | curses.A_BOLD))
        lines.append(("", 0))

        # Day column headers
        header_line = " " * time_col_width + "│"
        for day_offset in range(7):
            day_date = week_start + timedelta(days=day_offset)
            day_name = day_date.strftime("%a")
            day_num = day_date.day
            is_today = day_date == today

            # Dynamic header based on column width
            if day_col_width >= 15:
                day_label = day_date.strftime("%a %b %d")
            else:
                day_label = f"{day_name} {day_num}"

            if is_today:
                cell = f"[{day_label:^{day_col_width-2}}]│"
            else:
                cell = f"{day_label:^{day_col_width}}│"
            header_line += cell

        lines.append((header_line, curses.color_pair(self.COLOR_HEADER) | curses.A_BOLD))

        # Separator under header
        sep = "─" * time_col_width + "┼" + ("─" * day_col_width + "┼") * 6 + "─" * day_col_width + "┤"
        lines.append((sep, curses.color_pair(self.COLOR_DIM)))

        # All-day events row
        allday_row = "ALLDY │"
        for day_offset in range(7):
            day_date = week_start + timedelta(days=day_offset)
            date_key = day_date.strftime("%Y-%m-%d")
            day_events = grouped.get(date_key, [])
            allday_events = [e for e in day_events if e['is_all_day']]

            if allday_events:
                # Show first all-day event title (truncated to fit cell)
                max_title = day_col_width - 2
                title = allday_events[0]['summary'][:max_title]
                if len(allday_events) > 1:
                    more = f" +{len(allday_events) - 1}"
                    if len(title) + len(more) <= max_title:
                        title += more
                    else:
                        title = title[:max_title - len(more)] + more
                cell = f" {title:<{day_col_width - 1}}│"
            else:
                cell = " " * day_col_width + "│"
            allday_row += cell

        lines.append((allday_row, curses.color_pair(self.COLOR_ALLDAY)))

        # Separator after all-day
        lines.append((sep, curses.color_pair(self.COLOR_DIM)))

        # Build a map of events by hour for quick lookup
        # For each day, track which hours have which events
        event_grid = {}  # (day_offset, hour) -> list of events
        for day_offset in range(7):
            day_date = week_start + timedelta(days=day_offset)
            date_key = day_date.strftime("%Y-%m-%d")
            day_events = grouped.get(date_key, [])

            for event in day_events:
                if event['is_all_day']:
                    continue

                start_hour = event['start'].hour
                end_hour = event['end'].hour
                if event['end'].minute > 0:
                    end_hour += 1  # Round up

                for hour in range(start_hour, max(end_hour, start_hour + 1)):
                    if WEEK_HOUR_START <= hour < WEEK_HOUR_END:
                        key = (day_offset, hour)
                        if key not in event_grid:
                            event_grid[key] = []
                        if event not in event_grid[key]:
                            event_grid[key].append(event)

        # Hourly rows
        for hour in range(WEEK_HOUR_START, WEEK_HOUR_END):
            # Time label
            if TIME_FORMAT == "12":
                if hour == 0:
                    time_label = "12 AM"
                elif hour < 12:
                    time_label = f"{hour:2d} AM"
                elif hour == 12:
                    time_label = "12 PM"
                else:
                    time_label = f"{hour - 12:2d} PM"
            else:
                time_label = f"{hour:02d}:00"

            # Render multiple rows per hour
            for row_in_hour in range(rows_per_hour):
                if row_in_hour == 0:
                    hour_row = f"{time_label:>5} │"
                else:
                    hour_row = f"{'':>5} │"  # Empty time label for subsequent rows

                for day_offset in range(7):
                    key = (day_offset, hour)
                    events_this_hour = event_grid.get(key, [])

                    if events_this_hour:
                        max_title = day_col_width - 2

                        if row_in_hour < len(events_this_hour):
                            # Show event at this row index
                            event = events_this_hour[row_in_hour]
                            if event['start'].hour == hour:
                                title = event['summary'][:max_title]
                                cell = f" {title:<{day_col_width - 1}}│"
                            else:
                                # Continuation
                                cell = f" {self.get_symbol('continuation'):<{day_col_width - 1}}│"
                        elif row_in_hour == 0 and events_this_hour:
                            # First row, show first event
                            event = events_this_hour[0]
                            if event['start'].hour == hour:
                                title = event['summary'][:max_title]
                                if len(events_this_hour) > rows_per_hour:
                                    more = f" +{len(events_this_hour) - rows_per_hour}"
                                    if len(title) + len(more) <= max_title:
                                        title += more
                                cell = f" {title:<{day_col_width - 1}}│"
                            else:
                                cell = f" {self.get_symbol('continuation'):<{day_col_width - 1}}│"
                        else:
                            # Empty row within hour block
                            cell = " " * day_col_width + "│"
                    else:
                        cell = " " * day_col_width + "│"

                    hour_row += cell

                lines.append((hour_row, curses.color_pair(self.COLOR_TIME)))

        return lines

    def render_header(self, height: int, width: int):
        """Render the header section with controls below."""
        now = now_local()

        # View indicator
        view_indicators = {'agenda': '[A]', 'month': '[M]', 'week': '[W]'}
        view_ind = view_indicators.get(self.current_view, '[?]')

        # Full width header
        header_width = width - 4

        border_top = f"╔{'═' * header_width}╗"
        border_bot = f"╚{'═' * header_width}╝"

        # Date and time
        date_str = now.strftime("%b %d, %Y").upper()
        time_str = now.strftime("%I:%M:%S %p")
        weekday = now.strftime("%A").upper()

        # Three sections: left (date/time), center (title), right (view indicator)
        left_content = f" {date_str}  {time_str}  {weekday}"
        center_content = f"{self.get_symbol('calendar')} {self.title}"
        right_content = f"{view_ind} "

        # Calculate spacing for three sections
        total_content = len(left_content) + len(center_content) + len(right_content)
        total_padding = header_width - total_content

        left_pad = total_padding // 2
        right_pad = total_padding - left_pad

        title_line = f"║{left_content}{' ' * left_pad}{center_content}{' ' * right_pad}{right_content}║"

        # Build controls line
        if self.current_view == 'month':
            controls = "q:Quit  ←→:Months  a:Agenda  w:Week  r:Refresh"
        elif self.current_view == 'week':
            controls = "q:Quit  ←→:Weeks  a:Agenda  m:Month  r:Refresh"
        else:
            controls = "q:Quit  ↑↓:Scroll  a:Agenda  m:Month  w:Week  r:Refresh"
        if CAL_QUICKADD_URL:
            controls += "  F2:Add"

        # Status info
        if self.client.last_error:
            status = f"ERROR: {self.client.last_error}"
        else:
            if self.client.last_fetch:
                # Use configured timezone for consistency
                tz = get_local_tz()
                if tz:
                    last_update = datetime.fromtimestamp(self.client.last_fetch, tz=tz).strftime("%H:%M:%S")
                else:
                    last_update = datetime.fromtimestamp(self.client.last_fetch).strftime("%H:%M:%S")
            else:
                last_update = "Never"
            status = f"Updated: {last_update}"

        # Controls line with status
        controls_line = f"  {controls}    {status}"

        try:
            self.stdscr.addstr(0, 1, border_top[:width-2], curses.color_pair(self.COLOR_HEADER))
            self.stdscr.addstr(1, 1, title_line[:width-2], curses.color_pair(self.COLOR_HEADER) | curses.A_BOLD)
            self.stdscr.addstr(2, 1, border_bot[:width-2], curses.color_pair(self.COLOR_HEADER))
            self.stdscr.addstr(3, 0, controls_line[:width-1], curses.color_pair(self.COLOR_EVENT))
        except curses.error:
            pass

    def render_content(self, height: int, width: int):
        """Render the scrollable content area."""
        content_start = 5  # After header (3 rows) + controls (1 row) + gap (1 row)
        content_height = height - content_start - 1  # Use almost full height, no footer needed

        # Clamp scroll offset
        max_scroll = max(0, len(self.content_lines) - content_height)
        self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))

        # Render visible lines
        visible_lines = self.content_lines[self.scroll_offset:self.scroll_offset + content_height]

        for i, (line, attr) in enumerate(visible_lines):
            try:
                # Truncate line to fit width
                display_line = line[:width - 2]
                self.stdscr.addstr(content_start + i, 1, display_line, attr)
            except curses.error:
                pass

    def render_footer(self, height: int, width: int):
        """Footer is now rendered as part of header - this method is kept for compatibility."""
        pass

    # ── Quick Add Modal ───────────────────────────────────────────────────

    def _draw_modal_box(self, y: int, x: int, h: int, w: int, title: str, color: int):
        """Draw a bordered box with a centered title."""
        attr = curses.color_pair(color)
        # Top border with title
        if self.use_unicode:
            top = "╔" + "═" * (w - 2) + "╗"
            bot = "╚" + "═" * (w - 2) + "╝"
            side = "║"
        else:
            top = "+" + "-" * (w - 2) + "+"
            bot = "+" + "-" * (w - 2) + "+"
            side = "|"
        try:
            self.stdscr.addstr(y, x, top[:w], attr)
            # Insert title into top border
            if title:
                t = f" {title} "
                tx = x + (w - len(t)) // 2
                self.stdscr.addstr(y, tx, t, attr | curses.A_BOLD)
            # Side borders and blank interior
            for row in range(1, h - 1):
                self.stdscr.addstr(y + row, x, side, attr)
                self.stdscr.addstr(y + row, x + 1, " " * (w - 2), curses.color_pair(self.COLOR_EVENT))
                self.stdscr.addstr(y + row, x + w - 1, side, attr)
            self.stdscr.addstr(y + h - 1, x, bot[:w], attr)
        except curses.error:
            pass

    def render_modal(self, height: int, width: int):
        """Render the active modal overlay."""
        if self.modal_state == "input":
            self._render_input_modal(height, width)
        elif self.modal_state == "sending":
            self._render_sending_modal(height, width)
            # Check if thread finished
            if self.quickadd_thread and not self.quickadd_thread.is_alive():
                self.modal_state = "result"
                self.quickadd_thread = None
        elif self.modal_state == "result":
            self._render_result_modal(height, width)

    def _render_input_modal(self, height: int, width: int):
        """Draw the text input box at the bottom of the screen."""
        box_w = min(width - 4, 70)
        box_h = 3
        box_x = (width - box_w) // 2
        box_y = height - box_h - 1

        self._draw_modal_box(box_y, box_x, box_h, box_w, "Quick Add Event", self.COLOR_ACCENT)

        # Input line
        prompt = "> "
        max_text = box_w - 4 - len(prompt)
        # Scroll input if longer than visible area
        visible_start = max(0, self.input_cursor - max_text + 1)
        visible_text = self.input_buffer[visible_start:visible_start + max_text]
        cursor_x = self.input_cursor - visible_start

        try:
            self.stdscr.addstr(box_y + 1, box_x + 2, prompt, curses.color_pair(self.COLOR_ACCENT))
            self.stdscr.addstr(box_y + 1, box_x + 2 + len(prompt), visible_text, curses.color_pair(self.COLOR_EVENT))
            # Position cursor
            curses.curs_set(1)
            self.stdscr.move(box_y + 1, box_x + 2 + len(prompt) + cursor_x)
        except curses.error:
            pass

        # Hint in bottom border
        hint = " Enter:Send  ESC:Cancel "
        try:
            hx = box_x + (box_w - len(hint)) // 2
            self.stdscr.addstr(box_y + box_h - 1, hx, hint, curses.color_pair(self.COLOR_ACCENT))
        except curses.error:
            pass

    def _render_sending_modal(self, height: int, width: int):
        """Draw sending indicator."""
        box_w = min(width - 4, 70)
        box_h = 3
        box_x = (width - box_w) // 2
        box_y = height - box_h - 1

        self._draw_modal_box(box_y, box_x, box_h, box_w, "Quick Add Event", self.COLOR_ACCENT)

        frames = ["|", "/", "-", "\\"]
        spinner = frames[int(time.time() * 4) % len(frames)]
        msg = f"Sending... {spinner}"
        try:
            curses.curs_set(0)
            self.stdscr.addstr(box_y + 1, box_x + 2, msg, curses.color_pair(self.COLOR_TIME))
        except curses.error:
            pass

    def _render_result_modal(self, height: int, width: int):
        """Draw result overlay centered on screen."""
        result = self.quickadd_result or {}
        lines = []

        if "error" in result:
            title = "Error"
            color = self.COLOR_ERROR
            lines.append(result["error"])
            lines.append("")
            lines.append('Try: "dentist friday 2pm"')
        elif result.get("status") == "created":
            title = "Event Created"
            color = self.COLOR_TIME
            parsed = result.get("parsed") or {}
            event = result.get("event") or {}
            summary = parsed.get("title", event.get("title", ""))
            date = parsed.get("date", "")
            t = parsed.get("start_time", "")
            person = parsed.get("person", "")
            line = summary
            if date:
                line += f" on {date}"
            if t:
                line += f" at {t}"
            check = get_symbol("bullet")
            lines.append(f"{check} {line}")
            if person:
                lines.append(f"  Calendar: {person}")
            msg = result.get("message", "")
            if msg:
                lines.append(f"  {msg}")
        elif result.get("status") == "needs_confirmation":
            title = "Low Confidence"
            color = self.COLOR_DATE
            parsed = result.get("parsed") or {}
            summary = parsed.get("title", "?")
            date = parsed.get("date", "?")
            t = parsed.get("start_time", "")
            line = f"? {summary} on {date}"
            if t:
                line += f" at {t}"
            lines.append(line)
            lines.append("(Not created - confidence too low)")
        else:
            title = "Could Not Parse"
            color = self.COLOR_ERROR
            lines.append(result.get("message", "Could not understand input"))
            lines.append("")
            lines.append('Try: "dentist friday 2pm"')

        box_w = min(width - 4, 60)
        # Truncate lines to fit
        lines = [l[:box_w - 6] for l in lines]
        box_h = len(lines) + 4  # borders + padding
        box_x = (width - box_w) // 2
        box_y = (height - box_h) // 2

        self._draw_modal_box(box_y, box_x, box_h, box_w, title, color)

        try:
            curses.curs_set(0)
            for i, line in enumerate(lines):
                self.stdscr.addstr(box_y + 2 + i, box_x + 3, line, curses.color_pair(self.COLOR_EVENT))
            # Hint
            hint = " Press any key to close "
            hx = box_x + (box_w - len(hint)) // 2
            self.stdscr.addstr(box_y + box_h - 1, hx, hint, curses.color_pair(color))
        except curses.error:
            pass

    def _handle_input_mode(self, key: int) -> bool:
        """Handle keys during text input modal."""
        if key == 27:  # ESC
            self.modal_state = None
            self.input_buffer = ""
            self.input_cursor = 0
            curses.curs_set(0)
        elif key in (10, 13, curses.KEY_ENTER):  # Enter
            if self.input_buffer.strip():
                self.modal_state = "sending"
                curses.curs_set(0)
                t = threading.Thread(target=self._quickadd_send, args=(self.input_buffer,), daemon=True)
                self.quickadd_thread = t
                t.start()
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if self.input_cursor > 0:
                self.input_buffer = self.input_buffer[:self.input_cursor - 1] + self.input_buffer[self.input_cursor:]
                self.input_cursor -= 1
        elif key == curses.KEY_DC:
            if self.input_cursor < len(self.input_buffer):
                self.input_buffer = self.input_buffer[:self.input_cursor] + self.input_buffer[self.input_cursor + 1:]
        elif key == curses.KEY_LEFT:
            self.input_cursor = max(0, self.input_cursor - 1)
        elif key == curses.KEY_RIGHT:
            self.input_cursor = min(len(self.input_buffer), self.input_cursor + 1)
        elif key == curses.KEY_HOME:
            self.input_cursor = 0
        elif key == curses.KEY_END:
            self.input_cursor = len(self.input_buffer)
        elif 32 <= key <= 126:  # Printable ASCII
            self.input_buffer = self.input_buffer[:self.input_cursor] + chr(key) + self.input_buffer[self.input_cursor:]
            self.input_cursor += 1
        return True

    def _handle_result_mode(self, key: int) -> bool:
        """Handle keys during result display - any key dismisses."""
        if key != -1:
            # Force calendar refresh if event was created
            if self.quickadd_result and self.quickadd_result.get("status") == "created":
                self.client.last_fetch = 0
            self.modal_state = None
            self.quickadd_result = None
            self.input_buffer = ""
            self.input_cursor = 0
            curses.curs_set(0)
        return True

    def _quickadd_send(self, text: str):
        """Send quick-add request to cal-quickadd service (runs in thread)."""
        try:
            url = f"{CAL_QUICKADD_URL.rstrip('/')}/add"
            data = json.dumps({"text": text, "source": "console-tui"}).encode()
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                self.quickadd_result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode())
                self.quickadd_result = {"error": body.get("detail", f"HTTP {e.code}")}
            except Exception:
                self.quickadd_result = {"error": f"HTTP {e.code}"}
        except urllib.error.URLError as e:
            self.quickadd_result = {"error": f"Connection failed: {e.reason}"}
        except socket.timeout:
            self.quickadd_result = {"error": "Request timed out"}
        except Exception as e:
            self.quickadd_result = {"error": str(e)}
        self.modal_state = "result"

    def render(self, events: list):
        """Full screen render."""
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()

        if height < 10 or width < 40:
            try:
                self.stdscr.addstr(0, 0, "Terminal too small!", curses.color_pair(self.COLOR_ERROR))
            except curses.error:
                pass
            self.stdscr.refresh()
            return

        # Check minimum widths for grid views and fall back to agenda if too small
        effective_view = self.current_view
        min_month_width = 62  # 7 cols * 8 chars + borders
        min_week_width = 84   # 7 cols * 10 chars + time col + borders

        if self.current_view == 'month' and width < min_month_width:
            effective_view = 'agenda'
        elif self.current_view == 'week' and width < min_week_width:
            effective_view = 'agenda'

        # Temporarily override view for rendering if terminal too small
        original_view = self.current_view
        self.current_view = effective_view

        self.content_lines = self.build_content(events)

        self.render_header(height, width)
        self.render_content(height, width)
        self.render_footer(height, width)

        if self.modal_state is not None:
            self.render_modal(height, width)

        # Restore original view
        self.current_view = original_view

        self.stdscr.refresh()

    def handle_input(self) -> bool:
        """Handle keyboard input. Returns False to quit."""
        try:
            key = self.stdscr.getch()
        except curses.error:
            return True

        # Modal input delegation
        if self.modal_state == "input":
            return self._handle_input_mode(key)
        if self.modal_state == "sending":
            return True  # Ignore all keys while sending
        if self.modal_state == "result":
            return self._handle_result_mode(key)

        height, _ = self.stdscr.getmaxyx()
        page_size = height - 6  # Match content_height calculation (content_start=5, minus 1)

        if key == ord('q') or key == 27:  # q or ESC
            return False

        # Quick add
        elif key == curses.KEY_F2:
            if CAL_QUICKADD_URL:
                self.modal_state = "input"
                self.input_buffer = ""
                self.input_cursor = 0

        # View switching
        elif key == ord('m'):
            self.current_view = 'month'
            self.view_offset = 0
            self.scroll_offset = 0
        elif key == ord('w'):
            self.current_view = 'week'
            self.view_offset = 0
            self.scroll_offset = 0
        elif key == ord('a'):
            self.current_view = 'agenda'
            self.view_offset = 0
            self.scroll_offset = 0

        # Navigation - Left/Right for month/week views
        elif key == curses.KEY_LEFT or key == ord('h'):
            if self.current_view in ('month', 'week'):
                self.view_offset -= 1
                self.scroll_offset = 0
        elif key == curses.KEY_RIGHT or key == ord('l'):
            if self.current_view in ('month', 'week'):
                self.view_offset += 1
                self.scroll_offset = 0

        # Scrolling - Up/Down
        elif key == curses.KEY_UP or key == ord('k'):
            self.scroll_offset = max(0, self.scroll_offset - 1)
        elif key == curses.KEY_DOWN or key == ord('j'):
            self.scroll_offset += 1
        elif key == curses.KEY_PPAGE:  # Page Up
            self.scroll_offset = max(0, self.scroll_offset - page_size)
        elif key == curses.KEY_NPAGE:  # Page Down
            self.scroll_offset += page_size
        elif key == curses.KEY_HOME:
            self.scroll_offset = 0
            self.view_offset = 0  # Also reset to current month/week
        elif key == curses.KEY_END:
            self.scroll_offset = max(0, len(self.content_lines) - page_size)
        elif key == ord('r'):  # Force refresh
            self.client.last_fetch = 0

        return True

    def run(self):
        """Main event loop."""
        events = []
        last_render = 0

        while self.running:
            # Refresh data from API if needed
            if self.client.should_refresh():
                events = self.client.get_events(self.calendar_entity, DAYS_AHEAD)

            # Render screen
            now = time.time()
            if now - last_render >= SCREEN_REFRESH_INTERVAL:
                self.render(events)
                last_render = now

            # Handle input
            if not self.handle_input():
                break

            # Small sleep to prevent CPU spinning
            time.sleep(0.05)


# ═══════════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

def main(stdscr):
    """Main function wrapped for curses."""
    if not HA_TOKEN:
        stdscr.addstr(0, 0, "ERROR: HOMEASSISTANT_LONG_LIVE_TOKEN not set")
        stdscr.addstr(1, 0, "Please set the environment variable and try again.")
        stdscr.addstr(3, 0, "Press any key to exit...")
        stdscr.nodelay(False)
        stdscr.getch()
        return

    client = HACalendarClient(HA_URL, HA_TOKEN)

    # Try to detect calendar entity if not specified
    if CALENDAR_ENTITY == "calendar.family_calendar":
        calendars = client.list_calendars()
        if calendars:
            # Prefer calendars with 'family' in the name
            for cal in calendars:
                name = cal.get('name', '').lower()
                entity = cal.get('entity_id', '')
                if 'family' in name:
                    calendar_entity = entity
                    break
            else:
                # Use first calendar
                calendar_entity = calendars[0].get('entity_id', CALENDAR_ENTITY)
        else:
            calendar_entity = CALENDAR_ENTITY
    else:
        calendar_entity = CALENDAR_ENTITY

    # Get calendar name for title (use env var if set, otherwise from HA)
    if CALENDAR_TITLE != "FAMILY CALENDAR":
        title = CALENDAR_TITLE
    else:
        calendars = client.list_calendars()
        title = CALENDAR_TITLE
        for cal in calendars:
            if cal.get('entity_id') == calendar_entity:
                title = cal.get('name', CALENDAR_TITLE).upper()
                break

    ui = CalendarUI(stdscr, client, calendar_entity, title)
    ui.run()


def run():
    """Entry point that sets up curses."""
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
