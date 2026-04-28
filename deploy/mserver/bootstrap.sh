#!/usr/bin/env bash
# Idempotent bootstrap for the TUI on mserver (kiosk on tty1, user displayuser).
#
# What this does:
#   1. Syncs ha_calendar_console.py + cc_env.py to /home/displayuser/ha-calendar/
#   2. Optionally installs the systemd unit (set INSTALL_TUI_SERVICE=yes)
#
# What this does NOT do:
#   - Touch the existing .env (preserved)
#   - Configure agetty autologin (already configured on mserver)
#   - Reach across to nserver — cal-quickadd lives there, see deploy/nserver/

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TARGET_DIR="/home/displayuser/ha-calendar"

echo "==> Syncing TUI files to $TARGET_DIR..."
sudo install -o displayuser -g displayuser -m 755 \
  "$REPO_ROOT/ha_calendar_console.py" "$TARGET_DIR/ha_calendar_console.py"
sudo install -o displayuser -g displayuser -m 644 \
  "$REPO_ROOT/cc_env.py" "$TARGET_DIR/cc_env.py"

if [[ "${INSTALL_TUI_SERVICE:-no}" == "yes" ]]; then
  echo "==> Installing TUI systemd unit..."
  sudo cp "$(dirname "$0")/ha-calendar-console.service" /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable ha-calendar-console
  echo "    Run 'sudo systemctl restart ha-calendar-console' when ready."
else
  echo "==> Skipping systemd unit install (set INSTALL_TUI_SERVICE=yes to enable)."
  echo "    For now, kill the running process so the bash-profile loop respawns it:"
  echo "      sudo pkill -f ha_calendar_console.py"
fi

echo "Done."
