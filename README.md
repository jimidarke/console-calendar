# Console Calendar

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

This repo ships **two components** that work together but are deployed independently:

1. **Console TUI** (`ha_calendar_console.py`) — a curses agenda display that reads from Home Assistant. Runs bare-metal on a TTY (kiosk autologin). Zero runtime dependencies (Python stdlib only).
2. **cal-quickadd** (`cal-quickadd/`) — a FastAPI service that turns natural language ("jonnie soccer thursday 445pm") and images into Google Calendar events using Gemini. Runs in Docker.

The TUI integrates with cal-quickadd via the `F2` key when `CAL_QUICKADD_URL` is set; both can run on the same host. See [`deploy/mserver/`](deploy/mserver/) for a single-host deploy.

---

An htop-like terminal UI for displaying your Home Assistant calendar agenda. Perfect for headless servers, kiosk displays, Raspberry Pi projects, or anyone who loves the terminal.

```
╔══════════════════════════════════════════════════════════════════════╗
║ JAN 08, 2026  09:45:32 PM  📅        FAMILY CALENDAR                 ║
╚══════════════════════════════════════════════════════════════════════╝

────────────────────────────────────────────────────────────
 ★ TODAY WEDNESDAY - JANUARY 08, 2026
────────────────────────────────────────────────────────────
   7:00 AM        ► Morning Standup
   9:30 AM        ► Dentist Appointment
                  @ Downtown Dental Clinic
   3:30 PM        ► School Pickup

────────────────────────────────────────────────────────────
 ★ TOMORROW THURSDAY - JANUARY 09, 2026
────────────────────────────────────────────────────────────
   [▓ ALL DAY]     Weekend Trip
                   @ Mountain Resort
   6:00 PM        ► Pack for Trip

────────────────────────────────────────────────────────────
 ★ FRIDAY - JANUARY 10, 2026
────────────────────────────────────────────────────────────
   [▓ ALL DAY]     Weekend Trip
   6:15 PM        ► Evening Class

 [  0%] Last update: 21:45:32        q:Quit  ↑↓:Scroll  r:Refresh
```

## Features

- **Three views** - Agenda (scrolling list), Month (calendar grid), and Week (7-day hourly planner)
- **Full-screen terminal UI** - Like htop, runs in your terminal with colors and scrolling
- **Real-time updates** - Clock updates every second, calendar refreshes every minute
- **All-day event support** - Clearly marked with special formatting
- **Location display** - Optional display of event locations
- **Kiosk mode** - Auto-start on boot for dedicated displays
- **Zero dependencies** - Uses only Python standard library (curses, urllib)
- **Unicode & ASCII modes** - Works on any terminal
- **Vim-style navigation** - `h`/`j`/`k`/`l` for navigation

## Use Cases

- **Server room monitor** - Replace htop with something useful on that always-on display
- **Kitchen dashboard** - Raspberry Pi + old monitor = family command center
- **Office kiosk** - Conference room availability at a glance
- **Home automation display** - Pair with other HA dashboards
- **SSH check-in** - Quick calendar glance when you SSH into your server

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/jimidarke/console-calendar.git
cd console-calendar

# Copy and edit configuration
cp .env.example .env
nano .env
```

### 2. Get Home Assistant Token

1. Open Home Assistant web UI
2. Click your profile (bottom left)
3. Go to **Security** tab
4. Scroll to **Long-Lived Access Tokens**
5. Click **Create Token**, name it "Console Calendar"
6. Copy the token to your `.env` file

```bash
# Example .env
HOMEASSISTANT_URL=http://192.168.1.100:8123
HOMEASSISTANT_LONG_LIVE_TOKEN=eyJhbGciOiJIUzI1NiIs...
HA_CALENDAR_ENTITY=calendar.family
```

### 3. Find Your Calendar Entity

```bash
# List available calendars from Home Assistant
python3 ha_list_calendars.py
```

Example output:
```
╔════════════════════════════════════════════════════════════════╗
║           AVAILABLE HOME ASSISTANT CALENDARS                   ║
╠════════════════════════════════════════════════════════════════╣
║  calendar.family                      Family Calendar          ║
║  calendar.work                        Work Calendar            ║
║  calendar.holidays                    US Holidays              ║
╚════════════════════════════════════════════════════════════════╝
```

### 4. Test Connection

```bash
# Verify everything works before running the UI
python3 test_ha_calendar.py
```

### 5. Run

```bash
# Using the launcher script
./run_calendar.sh

# Or directly
python3 ha_calendar_console.py
```

## Configuration

All configuration is done via environment variables in `.env`. The app auto-loads this file from its directory.

### Required Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `HOMEASSISTANT_URL` | Your HA instance URL | `http://192.168.1.100:8123` |
| `HOMEASSISTANT_LONG_LIVE_TOKEN` | Long-lived access token | `eyJhbGci...` |

### Calendar Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `HA_CALENDAR_ENTITY` | `calendar.family` | Calendar entity ID to display |
| `HA_CALENDAR_TITLE` | `FAMILY CALENDAR` | Custom title in header |
| `HA_DAYS_AHEAD` | `60` | Number of days of events to fetch |

### Display Options

| Variable | Default | Description |
|----------|---------|-------------|
| `HA_USE_UNICODE` | `true` | Use Unicode symbols (★, ►, ●) |
| `HA_TIME_FORMAT` | `12` | Time format: `12` or `24` |
| `HA_SHOW_LOCATIONS` | `true` | Show event locations |
| `HA_SHOW_DESCRIPTIONS` | `false` | Show event descriptions |
| `HA_TIMEZONE` | (system) | IANA timezone name (e.g. `America/Edmonton`) |

### View Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `HA_DEFAULT_VIEW` | `agenda` | Starting view: `agenda`, `month`, or `week` |
| `HA_WEEK_START` | `monday` | Week start day: `monday` or `sunday` |
| `HA_WEEK_HOUR_START` | `7` | First hour shown in week view (24h) |
| `HA_WEEK_HOUR_END` | `21` | Last hour shown in week view (24h) |

### Refresh Intervals

| Variable | Default | Description |
|----------|---------|-------------|
| `HA_API_REFRESH_INTERVAL` | `60` | Seconds between API calls |
| `HA_SCREEN_REFRESH_INTERVAL` | `1` | Seconds between screen redraws |

### Example Configurations

**Minimal Setup:**
```bash
HOMEASSISTANT_URL=http://homeassistant.local:8123
HOMEASSISTANT_LONG_LIVE_TOKEN=your_token_here
HA_CALENDAR_ENTITY=calendar.family
```

**Work Calendar with 24h Time:**
```bash
HOMEASSISTANT_URL=https://ha.company.com
HOMEASSISTANT_LONG_LIVE_TOKEN=your_token_here
HA_CALENDAR_ENTITY=calendar.work
HA_CALENDAR_TITLE=TEAM SCHEDULE
HA_TIME_FORMAT=24
HA_DAYS_AHEAD=14
```

**Low-bandwidth/Slow Connection:**
```bash
HOMEASSISTANT_URL=http://192.168.1.100:8123
HOMEASSISTANT_LONG_LIVE_TOKEN=your_token_here
HA_CALENDAR_ENTITY=calendar.family
HA_API_REFRESH_INTERVAL=300
HA_SHOW_LOCATIONS=false
HA_SHOW_DESCRIPTIONS=false
```

**ASCII-only Terminal:**
```bash
HOMEASSISTANT_URL=http://192.168.1.100:8123
HOMEASSISTANT_LONG_LIVE_TOKEN=your_token_here
HA_CALENDAR_ENTITY=calendar.family
HA_USE_UNICODE=false
```

## Controls

| Key | Action |
|-----|--------|
| `a` | Agenda view (scrolling list) |
| `m` | Month view (calendar grid) |
| `w` | Week view (hourly planner) |
| `←` / `h` | Previous month/week (in month/week views) |
| `→` / `l` | Next month/week (in month/week views) |
| `↑` / `k` | Scroll up |
| `↓` / `j` | Scroll down |
| `PgUp` | Page up |
| `PgDn` | Page down |
| `Home` | Jump to top / reset to current period |
| `End` | Jump to bottom |
| `r` | Force refresh from API |
| `q` / `ESC` | Quit |

## Kiosk Mode Setup

Turn any Linux machine into a dedicated calendar display.

### Prerequisites

- Linux system with a TTY (physical or virtual console)
- A user account for the kiosk (e.g., `kiosk`)
- Root/sudo access for installation

### Check Existing Configuration

First, see what auto-start configs already exist:

```bash
sudo ./setup_kiosk.sh check
```

Example output:
```
═══════════════════════════════════════════════════════════════════
  CHECKING FOR EXISTING AUTO-START CONFIGURATIONS
═══════════════════════════════════════════════════════════════════

[WARN] Found: Auto-start command in .bash_profile
       File: /home/kiosk/.bash_profile
       Matching lines:
         15:    htop

───────────────────────────────────────────────────────────────────
[WARN] Existing configurations found (will be backed up during install)
```

### Install Kiosk Mode

```bash
# Install with default settings (user: kiosk, tty: tty1)
sudo ./setup_kiosk.sh install

# Or customize the user and TTY
sudo KIOSK_USER=pi KIOSK_TTY=tty1 ./setup_kiosk.sh install
```

This will:
1. Back up existing auto-start configurations to `~/.kiosk-backup-TIMESTAMP/`
2. Copy calendar files to `/home/kiosk/ha-calendar/`
3. Set up auto-login on the specified TTY
4. Configure `.bash_profile` to launch calendar with auto-restart

### Test It

```bash
# Switch to TTY1 (on the physical console)
# Press: Ctrl+Alt+F1

# Or reboot to test full auto-start
sudo reboot
```

### Uninstall

```bash
sudo ./setup_kiosk.sh uninstall
```

Backups are preserved in `~/.kiosk-backup-*` directories.

### Raspberry Pi Example

```bash
# Create kiosk user
sudo useradd -m -s /bin/bash kiosk

# Clone and setup
sudo -u kiosk git clone https://github.com/jimidarke/console-calendar.git /home/kiosk/console-calendar
cd /home/kiosk/console-calendar

# Configure
sudo -u kiosk cp .env.example .env
sudo -u kiosk nano .env

# Install kiosk mode
sudo KIOSK_USER=kiosk ./setup_kiosk.sh install

# Reboot to test
sudo reboot
```

## File Structure

```
console-calendar/
├── ha_calendar_console.py        # TUI app (curses, stdlib only)
├── ha_list_calendars.py          # Utility: list available HA calendars
├── test_ha_calendar.py           # Utility: smoke-test HA API connectivity
├── cc_env.py                     # Shared .env loader (used by TUI and cal-quickadd)
├── run_calendar.sh               # Launcher script (sources .env)
├── setup_kiosk.sh                # Kiosk autologin installer
├── .env.example                  # TUI configuration template
├── systemd/                      # Reference systemd unit (legacy)
├── cal-quickadd/                 # FastAPI service (Gemini + Google Calendar)
│   ├── app/                      # main.py, ai_parser.py, calendar_api.py, config.py
│   ├── requirements.txt
│   ├── setup_oauth.py            # One-time interactive Google OAuth helper
│   ├── test_api.py               # FastAPI integration tests (some hit real Gemini)
│   ├── test_parser_retry.py      # Unit tests for retry/backoff/fallback (all mocked)
│   ├── Dockerfile, docker-compose.yml  # Legacy single-component deploy
│   └── SECURITY.md
├── deploy/
│   ├── mserver/                  # TUI bare-metal kiosk (tty1, displayuser)
│   │   ├── ha-calendar-console.service
│   │   └── bootstrap.sh
│   └── nserver/                  # cal-quickadd Docker host (port 8419)
│       ├── Dockerfile, docker-compose.yml, .env.example
│       └── bootstrap.sh
├── CLAUDE.md, LICENSE, README.md, VERSION.txt
```

## Production deploy

Two hosts, one repo:

- **mserver** runs the TUI bare-metal as user `displayuser` on `tty1` (autologin via `agetty`). Files live at `/home/displayuser/ha-calendar/`.
- **nserver** runs `cal-quickadd` as a Docker container on port `8419`, fronted by an existing nginx-proxy + DNS record.

The TUI talks to cal-quickadd over the network via `CAL_QUICKADD_URL`; the header shows a `[QA: ok | slow | auth! | quota | re-auth | down]` health pill that combines Gemini quota state and OAuth token age.

### nserver (cal-quickadd)

```bash
# On nserver, with this repo synced/cloned to /root/docker/console-calendar:
cd /root/docker/console-calendar
cp deploy/nserver/.env.example deploy/nserver/.env   # fill in real values
# Place Google OAuth credentials.json at deploy/nserver/config/credentials.json
# Place a freshly-minted token.json beside it (or run /tmp/refresh_oauth.py
# inside the running container after first start).
deploy/nserver/bootstrap.sh
```

The script is idempotent — re-running rebuilds the image and restarts. While the OAuth consent screen is in **Testing** status, refresh tokens expire every 7 days; the TUI pill goes amber (`auth!`) ~24-33h before expiry and red (`re-auth`) when dead. To re-mint:

```bash
docker exec -it cal-quickadd python /tmp/refresh_oauth.py
docker restart cal-quickadd
```

### mserver (TUI)

```bash
# On mserver, with this repo synced/cloned somewhere:
INSTALL_TUI_SERVICE=yes deploy/mserver/bootstrap.sh
```

This copies `ha_calendar_console.py` and `cc_env.py` into `/home/displayuser/ha-calendar/`, preserving the existing `.env`. With `INSTALL_TUI_SERVICE=yes` it also drops the systemd unit and enables it (replacing the bash-profile respawn loop). Without that flag it just syncs the files; the running process picks them up next restart.

## cal-quickadd

A FastAPI service that converts natural language and images into Google Calendar events.

### Endpoints

| Method | Path     | Purpose |
|--------|----------|---------|
| POST   | `/add`   | `{"text": "jonnie soccer thursday 445pm"}` → creates event |
| POST   | `/scan`  | multipart image upload (≤10 MB) → extracts and creates events |
| GET    | `/health`| liveness + Gemini quota state |
| GET    | `/`      | minimal web UI (`cal-quickadd/app/static/`) |

### Key behaviour

- **Retry/backoff on 429**: transient Gemini quota errors retry up to 3× with exponential backoff + jitter. On hard daily-quota exhaustion, falls back to `GEMINI_MODEL_FALLBACK` (default `gemini-1.5-flash`, separate quota bucket from `gemini-2.0-flash`). If both exhaust, the API returns **HTTP 429** with `Retry-After`.
- **Family-member calendar routing**: `FAMILY_CALENDARS` env (JSON `{"jonnie": "calendar-id", ...}`) routes events per person; falls back to `GOOGLE_CALENDAR_ID`.
- **Per-IP rate limit**: 30 POSTs / 60 s (FastAPI middleware).
- **Optional shared-secret auth**: set `CAL_TOKEN`; clients must send `X-Cal-Token: <value>`.
- **Health surface**: `/health` exposes `gemini_quota_state` (`ok|throttled|exhausted`) so the TUI can render a pill.

### Required env

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Gemini Flash API key |
| `GOOGLE_CALENDAR_ID` | Default calendar (usually your email) |
| `GOOGLE_CREDENTIALS_PATH`, `GOOGLE_TOKEN_PATH` | OAuth artifacts (default `/config/...`) |
| `GEMINI_MODEL_PRIMARY`, `GEMINI_MODEL_FALLBACK` | Model selection (defaults sane) |
| `FAMILY_MEMBERS`, `FAMILY_CALENDARS` | Routing config |
| `TIMEZONE` | IANA TZ for date resolution |
| `CAL_TOKEN` | Optional shared secret |

### Tests

```bash
cd cal-quickadd
pip install -r requirements.txt pytest pytest-asyncio httpx
GEMINI_API_KEY=test GOOGLE_CALENDAR_ID=test pytest test_parser_retry.py     # all mocked
GEMINI_API_KEY=real GOOGLE_CALENDAR_ID=real pytest test_api.py              # hits Gemini
```

### Security notes (formerly SECURITY.md)

- `/health` does NOT include event PII (this was fixed; was previously leaking the last-created event).
- Bind to `127.0.0.1` in production unless `CAL_TOKEN` is set; the LAN-binding default in the legacy compose is **not safe** without auth.
- 10 MB image cap on `/scan` is enforced by streaming + early bail-out, not after buffering.
- OAuth token is stored at `GOOGLE_TOKEN_PATH` with default permissions; ensure the `config/` host-mount is mode 700.

## Troubleshooting

### "Token not set" error

```bash
# Check your .env file exists and has the token
cat .env | grep TOKEN

# Make sure you're running from the right directory
cd /path/to/console-calendar
./run_calendar.sh
```

### "Connection error" or timeout

```bash
# Test connectivity to Home Assistant
curl -s http://your-ha-ip:8123/api/ \
  -H "Authorization: Bearer YOUR_TOKEN" | head

# Check if HA is accessible
ping your-ha-ip
```

### "No calendars found"

Make sure you have a calendar integration in Home Assistant:
- **Google Calendar** - Settings → Integrations → Add → Google Calendar
- **Local Calendar** - Settings → Integrations → Add → Local Calendar
- **CalDAV** - For iCloud, Nextcloud, etc.

### Display looks broken / weird characters

```bash
# Try ASCII mode
export HA_USE_UNICODE=false
python3 ha_calendar_console.py

# Check terminal encoding
echo $LANG
# Should be something like: en_US.UTF-8
```

### Terminal too small

Minimum size is 80 columns × 24 rows. Check with:
```bash
echo "Columns: $(tput cols), Rows: $(tput lines)"
```

### Events not updating

```bash
# Force refresh by pressing 'r' in the app

# Or reduce the refresh interval
export HA_API_REFRESH_INTERVAL=30
```

### SSH session disconnects and app stops

Use `tmux` or `screen` to keep it running:
```bash
tmux new-session -d -s calendar './run_calendar.sh'
tmux attach -t calendar
```

## Requirements

- **Python 3.8+** (uses `typing` features)
- **Home Assistant** with at least one calendar integration
- **Terminal** with curses support:
  - Linux: Any terminal
  - macOS: Terminal.app, iTerm2
  - Windows: WSL, Windows Terminal with WSL

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Roadmap

- [ ] Multiple calendar support (side-by-side or merged view)
- [ ] Weather widget integration
- [ ] Home Assistant sensor display widgets
- [ ] Custom color themes / config file
- [ ] Mouse support for scrolling
- [ ] Recurring event indicators
- [ ] Event countdown timer
- [ ] Notification sound on new events

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Inspired by [htop](https://htop.dev/) and other excellent TUI applications
- Built for [Home Assistant](https://www.home-assistant.io/) users
- Uses Python's built-in `curses` library

---

**Questions?** Open an issue on [GitHub](https://github.com/jimidarke/console-calendar/issues).
