#!/bin/bash
# Launch the Home Assistant Calendar Console
# This script sources the .env file and runs the console app

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

# Optional: Set calendar entity (uncomment and modify as needed)
# export HA_CALENDAR_ENTITY="calendar.my_calendar"

# Run the console app
exec python3 "$SCRIPT_DIR/ha_calendar_console.py"
