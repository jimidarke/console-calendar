#!/usr/bin/env python3
"""
Console Calendar - Home Assistant Calendar Display
An htop-like terminal UI for displaying family calendar agenda.

Usage:
    ./ha_calendar_console.py

Environment Variables:
    See .env.example for full list of configuration options.

Controls:
    q, ESC      - Quit
    UP/DOWN, j/k - Scroll
    PgUp/PgDn   - Scroll page
    Home/End    - Jump to top/bottom
    r           - Force refresh

Repository: https://github.com/jimidarke/console-calendar
"""

import curses
import os
import sys
import time
import urllib.request
import urllib.error
import json
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
DAYS_AHEAD = int(os.environ.get("HA_DAYS_AHEAD", "7"))

# Display Options
USE_UNICODE = os.environ.get("HA_USE_UNICODE", "true").lower() == "true"
TIME_FORMAT = os.environ.get("HA_TIME_FORMAT", "12")
SHOW_LOCATIONS = os.environ.get("HA_SHOW_LOCATIONS", "true").lower() == "true"
SHOW_DESCRIPTIONS = os.environ.get("HA_SHOW_DESCRIPTIONS", "false").lower() == "true"
TIMEZONE_NAME = os.environ.get("HA_TIMEZONE", "")

# Refresh Intervals
API_REFRESH_INTERVAL = int(os.environ.get("HA_API_REFRESH_INTERVAL", "60"))
SCREEN_REFRESH_INTERVAL = int(os.environ.get("HA_SCREEN_REFRESH_INTERVAL", "1"))


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
        """Build content lines with color attributes."""
        lines = []
        today = today_local()
        grouped = group_events_by_date(events)

        # Funky separator patterns
        separators = [
            "·═══════════════════════════════════════════════════════════·",
            "·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·~·",
            "·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·•·",
            "·◆·◇·◆·◇·◆·◇·◆·◇·◆·◇·◆·◇·◆·◇·◆·◇·◆·◇·◆·◇·◆·◇·◆·◇·◆·◇·◆·◇·◆·◇·",
            "·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·─·",
            "·▪·▫·▪·▫·▪·▫·▪·▫·▪·▫·▪·▫·▪·▫·▪·▫·▪·▫·▪·▫·▪·▫·▪·▫·▪·▫·▪·▫·▪·▫·",
            "·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·░·",
        ]

        # Generate dates for next DAYS_AHEAD days
        for day_offset in range(DAYS_AHEAD):
            current_date = today + timedelta(days=day_offset)
            date_key = current_date.strftime("%Y-%m-%d")

            # Day label
            if day_offset == 0:
                day_label = "TODAY"
            elif day_offset == 1:
                day_label = "TOMORROW"
            else:
                day_label = current_date.strftime("%A").upper()

            date_str = current_date.strftime("%B %d, %Y").upper()

            # Pick a separator pattern (cycle through them)
            sep = separators[day_offset % len(separators)]

            # Separator line
            lines.append(("", 0))
            lines.append((sep, curses.color_pair(self.COLOR_DIM) | curses.A_DIM))
            lines.append((f" {self.get_symbol('star')} {day_label} {current_date.strftime('%A').upper()} - {date_str}",
                         curses.color_pair(self.COLOR_DATE) | curses.A_BOLD))
            lines.append((sep, curses.color_pair(self.COLOR_DIM) | curses.A_DIM))

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

    def render_header(self, height: int, width: int):
        """Render the header section."""
        now = now_local()

        # Top border
        header_width = min(width - 2, 70)
        border_top = f"╔{'═' * header_width}╗"
        border_bot = f"╚{'═' * header_width}╝"

        # Date and time
        date_str = now.strftime("%b %d, %Y").upper()
        time_str = now.strftime("%I:%M:%S %p")
        weekday = now.strftime("%A").upper()

        # Title line
        title_line = f"║ {date_str}  {time_str}  {self.get_symbol('calendar')} {self.title:^30} ║"
        title_line = title_line[:header_width + 2]
        if len(title_line) < header_width + 2:
            title_line = title_line[:-1] + ' ' * (header_width + 2 - len(title_line)) + '║'

        try:
            self.stdscr.addstr(0, 1, border_top, curses.color_pair(self.COLOR_HEADER))
            self.stdscr.addstr(1, 1, title_line, curses.color_pair(self.COLOR_HEADER) | curses.A_BOLD)
            self.stdscr.addstr(2, 1, border_bot, curses.color_pair(self.COLOR_HEADER))
        except curses.error:
            pass

    def render_content(self, height: int, width: int):
        """Render the scrollable content area."""
        content_start = 4
        content_height = height - content_start - 2  # Leave room for footer

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
        """Render the footer with controls and status."""
        # Scroll indicator
        if self.content_lines:
            total = len(self.content_lines)
            visible = height - 6
            pos = self.scroll_offset
            pct = int((pos / max(1, total - visible)) * 100) if total > visible else 100
            scroll_info = f"[{pct:3d}%]"
        else:
            scroll_info = "[---]"

        # Status line
        if self.client.last_error:
            status = f"ERROR: {self.client.last_error}"
            status_attr = curses.color_pair(self.COLOR_ERROR)
        else:
            last_update = datetime.fromtimestamp(self.client.last_fetch).strftime("%H:%M:%S") if self.client.last_fetch else "Never"
            status = f"Last update: {last_update}"
            status_attr = curses.color_pair(self.COLOR_DIM)

        # Controls
        controls = "q:Quit  ↑↓:Scroll  PgUp/Dn:Page  r:Refresh"

        footer = f" {scroll_info} {status:<30} {controls}"

        try:
            self.stdscr.addstr(height - 1, 0, footer[:width - 1], curses.color_pair(self.COLOR_DIM))
        except curses.error:
            pass

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

        self.content_lines = self.build_content(events)

        self.render_header(height, width)
        self.render_content(height, width)
        self.render_footer(height, width)

        self.stdscr.refresh()

    def handle_input(self) -> bool:
        """Handle keyboard input. Returns False to quit."""
        try:
            key = self.stdscr.getch()
        except curses.error:
            return True

        height, _ = self.stdscr.getmaxyx()
        page_size = height - 6

        if key == ord('q') or key == 27:  # q or ESC
            return False
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
