#!/usr/bin/env python3
"""
Test script to verify Home Assistant calendar API connectivity.
Run this before using ha_calendar_console.py to ensure the API works.

Usage:
    python3 test_ha_calendar.py
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path


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
                    if key not in os.environ:
                        os.environ[key] = value


# Load .env on import
load_env_file()

HA_URL = os.environ.get("HOMEASSISTANT_URL", "http://192.168.1.40:8123")
HA_TOKEN = os.environ.get("HOMEASSISTANT_LONG_LIVE_TOKEN", "")


def make_request(endpoint: str) -> tuple[bool, any]:
    """Make authenticated request to HA API. Returns (success, data_or_error)."""
    url = f"{HA_URL.rstrip('/')}{endpoint}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {HA_TOKEN}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return True, json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Connection error: {e.reason}"
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def test_connection():
    """Test basic API connectivity."""
    print("=" * 60)
    print("TEST 1: API Connectivity")
    print("=" * 60)
    print(f"  URL: {HA_URL}")
    print(f"  Token: {'*' * 20}...{HA_TOKEN[-10:] if len(HA_TOKEN) > 10 else '(too short)'}")
    print()

    success, result = make_request("/api/")
    if success:
        print(f"  [PASS] Connected to Home Assistant")
        print(f"         Version: {result.get('version', 'unknown')}")
        return True
    else:
        print(f"  [FAIL] {result}")
        return False


def test_list_calendars():
    """Test listing available calendars."""
    print()
    print("=" * 60)
    print("TEST 2: List Calendars")
    print("=" * 60)

    success, result = make_request("/api/calendars")
    if not success:
        print(f"  [FAIL] {result}")
        return None

    if not result:
        print("  [WARN] No calendars found in Home Assistant")
        return None

    print(f"  [PASS] Found {len(result)} calendar(s):")
    print()
    for cal in result:
        entity_id = cal.get('entity_id', 'unknown')
        name = cal.get('name', 'Unnamed')
        print(f"         - {entity_id}")
        print(f"           Name: {name}")
        print()

    return result


def test_get_events(calendar_entity: str):
    """Test fetching events from a calendar."""
    print()
    print("=" * 60)
    print(f"TEST 3: Get Events from {calendar_entity}")
    print("=" * 60)

    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=8)

    start_str = start.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end.strftime("%Y-%m-%dT%H:%M:%S")

    endpoint = f"/api/calendars/{calendar_entity}?start={start_str}&end={end_str}"
    print(f"  Endpoint: {endpoint}")
    print(f"  Date range: {start.date()} to {end.date()}")
    print()

    success, result = make_request(endpoint)
    if not success:
        print(f"  [FAIL] {result}")
        return False

    print(f"  [PASS] Retrieved {len(result)} event(s)")
    print()

    if result:
        print("  Events:")
        print("  " + "-" * 56)
        for event in result[:10]:  # Show first 10
            summary = event.get('summary', 'Untitled')
            start_info = event.get('start', {})

            if 'date' in start_info:
                time_str = f"[ALL DAY] {start_info['date']}"
            else:
                dt_str = start_info.get('dateTime', '')
                try:
                    dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                    time_str = dt.strftime("%Y-%m-%d %I:%M %p")
                except:
                    time_str = dt_str[:19] if dt_str else 'unknown'

            print(f"    {time_str}")
            print(f"      {summary}")
            if event.get('location'):
                print(f"      @ {event['location']}")
            print()

        if len(result) > 10:
            print(f"  ... and {len(result) - 10} more events")
    else:
        print("  (No events in the next 7 days)")

    return True


def main():
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║     HOME ASSISTANT CALENDAR API TEST                     ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()

    # Check token
    if not HA_TOKEN:
        print("ERROR: HOMEASSISTANT_LONG_LIVE_TOKEN not set")
        print()
        print("Create a .env file with your Home Assistant token:")
        print("  cp .env.example .env")
        print("  nano .env")
        sys.exit(1)

    # Run tests
    if not test_connection():
        print()
        print("RESULT: Connection test failed. Check URL and token.")
        sys.exit(1)

    calendars = test_list_calendars()
    if not calendars:
        print()
        print("RESULT: No calendars available. Check Home Assistant calendar integrations.")
        sys.exit(1)

    # Test first calendar
    first_cal = calendars[0].get('entity_id')
    test_get_events(first_cal)

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("  All tests passed!")
    print()
    print("  To run the calendar console:")
    print("    ./run_calendar.sh")
    print()
    print(f"  Using calendar: {first_cal}")
    print("  (Change HA_CALENDAR_ENTITY in .env to use a different one)")
    print()


if __name__ == "__main__":
    main()
