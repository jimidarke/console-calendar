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
