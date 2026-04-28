#!/usr/bin/env python3
"""
List available Home Assistant calendars.
Useful for finding the correct entity ID for ha_calendar_console.py

Usage:
    python3 ha_list_calendars.py
"""

import os
import sys
import urllib.request
import urllib.error
import json
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))
from cc_env import load_env  # noqa: E402

load_env(Path(__file__).parent)

HA_URL = os.environ.get("HOMEASSISTANT_URL", "http://192.168.1.40:8123")
HA_TOKEN = os.environ.get("HOMEASSISTANT_LONG_LIVE_TOKEN", "")


def main():
    if not HA_TOKEN:
        print("ERROR: HOMEASSISTANT_LONG_LIVE_TOKEN not set", file=sys.stderr)
        print("Create a .env file with your token", file=sys.stderr)
        sys.exit(1)

    url = f"{HA_URL}/api/calendars"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {HA_TOKEN}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            calendars = json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"ERROR: HTTP {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Connection failed: {e.reason}", file=sys.stderr)
        sys.exit(1)

    print("╔════════════════════════════════════════════════════════════════╗")
    print("║           AVAILABLE HOME ASSISTANT CALENDARS                   ║")
    print("╠════════════════════════════════════════════════════════════════╣")

    if not calendars:
        print("║  No calendars found                                            ║")
    else:
        for cal in calendars:
            entity = cal.get('entity_id', 'unknown')
            name = cal.get('name', 'Unnamed')
            print(f"║  {entity:<35} {name:<25} ║")

    print("╚════════════════════════════════════════════════════════════════╝")
    print()
    print("To use a specific calendar, set:")
    print("  export HA_CALENDAR_ENTITY=\"calendar.your_calendar\"")


if __name__ == "__main__":
    main()
