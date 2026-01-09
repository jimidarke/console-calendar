#!/bin/bash
#
# Kiosk Setup Script for HA Calendar Console
#
# This script:
#   1. Checks for existing auto-start configurations (htop, etc.)
#   2. Backs up existing configs
#   3. Sets up auto-login and calendar console launch
#
# Usage:
#   ./setup_kiosk.sh [check|install|uninstall]
#
# Run on the target server as root or with sudo

set -e

# ═══════════════════════════════════════════════════════════════════════════════
# Auto-load .env file
# ═══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    # Parse .env file safely (handles values with spaces)
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        # Trim whitespace from key
        key=$(echo "$key" | xargs)
        # Only set if not already in environment
        if [[ -z "${!key}" ]]; then
            export "$key=$value"
        fi
    done < "$SCRIPT_DIR/.env"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration (can be overridden by .env or environment)
# ═══════════════════════════════════════════════════════════════════════════════

KIOSK_USER="${KIOSK_USER:-kiosk}"
KIOSK_TTY="${KIOSK_TTY:-tty1}"
INSTALL_DIR="${INSTALL_DIR:-/home/$KIOSK_USER/ha-calendar}"
BACKUP_DIR="/home/$KIOSK_USER/.kiosk-backup-$(date +%Y%m%d-%H%M%S)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Detection Functions
# ═══════════════════════════════════════════════════════════════════════════════

detect_existing_autostart() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  CHECKING FOR EXISTING AUTO-START CONFIGURATIONS"
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""

    local found_any=0

    # Check 1: Getty auto-login override
    local getty_override="/etc/systemd/system/getty@${KIOSK_TTY}.service.d/override.conf"
    if [[ -f "$getty_override" ]]; then
        warn "Found: Getty auto-login override"
        echo "       File: $getty_override"
        echo "       Contents:"
        sed 's/^/         /' "$getty_override"
        echo ""
        found_any=1
    fi

    # Check 2: User's .bash_profile
    local bash_profile="/home/$KIOSK_USER/.bash_profile"
    if [[ -f "$bash_profile" ]]; then
        if grep -qE "(htop|top|btop|glances|ha_calendar|console)" "$bash_profile" 2>/dev/null; then
            warn "Found: Auto-start command in .bash_profile"
            echo "       File: $bash_profile"
            echo "       Matching lines:"
            grep -nE "(htop|top|btop|glances|ha_calendar|console)" "$bash_profile" | sed 's/^/         /'
            echo ""
            found_any=1
        fi
    fi

    # Check 3: User's .bashrc
    local bashrc="/home/$KIOSK_USER/.bashrc"
    if [[ -f "$bashrc" ]]; then
        if grep -qE "(htop|top|btop|glances|ha_calendar|console)" "$bashrc" 2>/dev/null; then
            warn "Found: Auto-start command in .bashrc"
            echo "       File: $bashrc"
            echo "       Matching lines:"
            grep -nE "(htop|top|btop|glances|ha_calendar|console)" "$bashrc" | sed 's/^/         /'
            echo ""
            found_any=1
        fi
    fi

    # Check 4: User's .profile
    local profile="/home/$KIOSK_USER/.profile"
    if [[ -f "$profile" ]]; then
        if grep -qE "(htop|top|btop|glances|ha_calendar|console)" "$profile" 2>/dev/null; then
            warn "Found: Auto-start command in .profile"
            echo "       File: $profile"
            echo "       Matching lines:"
            grep -nE "(htop|top|btop|glances|ha_calendar|console)" "$profile" | sed 's/^/         /'
            echo ""
            found_any=1
        fi
    fi

    # Check 5: Systemd user services
    local user_services="/home/$KIOSK_USER/.config/systemd/user"
    if [[ -d "$user_services" ]]; then
        local service_files=$(find "$user_services" -name "*.service" 2>/dev/null)
        if [[ -n "$service_files" ]]; then
            warn "Found: User systemd services"
            echo "       Directory: $user_services"
            echo "       Services:"
            echo "$service_files" | sed 's/^/         /'
            echo ""
            found_any=1
        fi
    fi

    # Check 6: System-wide kiosk service
    if [[ -f "/etc/systemd/system/ha-calendar-console.service" ]]; then
        warn "Found: Existing ha-calendar-console.service"
        echo "       File: /etc/systemd/system/ha-calendar-console.service"
        echo ""
        found_any=1
    fi

    # Check 7: Running processes on tty1
    local tty_procs=$(ps aux | grep -E "tty1|$KIOSK_TTY" | grep -v grep | grep -vE "agetty|login" || true)
    if [[ -n "$tty_procs" ]]; then
        warn "Found: Processes running on $KIOSK_TTY"
        echo "$tty_procs" | sed 's/^/         /'
        echo ""
        found_any=1
    fi

    # Summary
    echo "───────────────────────────────────────────────────────────────────"
    if [[ $found_any -eq 0 ]]; then
        ok "No existing auto-start configurations detected"
    else
        warn "Existing configurations found (will be backed up during install)"
    fi
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
# Installation Functions
# ═══════════════════════════════════════════════════════════════════════════════

backup_existing() {
    info "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"

    # Backup files if they exist
    local files_to_backup=(
        "/home/$KIOSK_USER/.bash_profile"
        "/home/$KIOSK_USER/.bashrc"
        "/home/$KIOSK_USER/.profile"
        "/etc/systemd/system/getty@${KIOSK_TTY}.service.d/override.conf"
        "/etc/systemd/system/ha-calendar-console.service"
    )

    for file in "${files_to_backup[@]}"; do
        if [[ -f "$file" ]]; then
            local backup_path="$BACKUP_DIR/$(basename $file)"
            cp "$file" "$backup_path"
            info "Backed up: $file -> $backup_path"
        fi
    done

    ok "Backup complete: $BACKUP_DIR"
}

install_calendar_files() {
    info "Installing calendar console files to $INSTALL_DIR"

    # Create install directory
    mkdir -p "$INSTALL_DIR"

    # Copy files from current directory (assumes running from repo)
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    if [[ -f "$script_dir/ha_calendar_console.py" ]]; then
        cp "$script_dir/ha_calendar_console.py" "$INSTALL_DIR/"
        chmod +x "$INSTALL_DIR/ha_calendar_console.py"
        ok "Copied ha_calendar_console.py"
    else
        error "ha_calendar_console.py not found in $script_dir"
        exit 1
    fi

    # Copy .env if it exists
    if [[ -f "$script_dir/.env" ]]; then
        cp "$script_dir/.env" "$INSTALL_DIR/"
        chmod 600 "$INSTALL_DIR/.env"
        ok "Copied .env (permissions set to 600)"
    else
        warn ".env not found - you'll need to create it manually"
    fi

    # Set ownership
    chown -R "$KIOSK_USER:$KIOSK_USER" "$INSTALL_DIR"

    ok "Files installed to $INSTALL_DIR"
}

setup_autologin() {
    info "Setting up auto-login for $KIOSK_USER on $KIOSK_TTY"

    # Create getty override directory
    local override_dir="/etc/systemd/system/getty@${KIOSK_TTY}.service.d"
    mkdir -p "$override_dir"

    # Create override config
    cat > "$override_dir/override.conf" << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $KIOSK_USER --noclear %I \$TERM
EOF

    ok "Created auto-login override: $override_dir/override.conf"
}

setup_autostart() {
    info "Setting up auto-start in .bash_profile"

    local bash_profile="/home/$KIOSK_USER/.bash_profile"

    # Remove existing auto-start lines (htop, etc.)
    if [[ -f "$bash_profile" ]]; then
        # Comment out existing htop/console lines instead of deleting
        sed -i 's/^\([^#].*\(htop\|btop\|top\|glances\).*\)$/# DISABLED: \1/' "$bash_profile"
    fi

    # Create/update .bash_profile with calendar launch
    cat > "$bash_profile" << 'EOF'
# ═══════════════════════════════════════════════════════════════════════════════
# Kiosk Auto-Start Configuration
# Generated by setup_kiosk.sh
# ═══════════════════════════════════════════════════════════════════════════════

# Only run on login shells on tty1
if [[ "$(tty)" == "/dev/tty1" ]] && [[ -z "$DISPLAY" ]]; then

    # Load environment variables
    if [[ -f ~/ha-calendar/.env ]]; then
        export $(grep -v '^#' ~/ha-calendar/.env | xargs)
    fi

    # Clear screen and show startup message
    clear
    echo "Starting Home Assistant Calendar Console..."
    sleep 1

    # Launch calendar console (loop to restart on exit)
    while true; do
        python3 ~/ha-calendar/ha_calendar_console.py

        # If it exits, show message and restart after delay
        echo ""
        echo "Calendar console exited. Restarting in 5 seconds..."
        echo "Press Ctrl+C to drop to shell"
        sleep 5
    done
fi

# Standard profile stuff for non-kiosk sessions
if [[ -f ~/.bashrc ]]; then
    . ~/.bashrc
fi
EOF

    chown "$KIOSK_USER:$KIOSK_USER" "$bash_profile"
    chmod 644 "$bash_profile"

    ok "Created .bash_profile with calendar auto-start"
}

reload_systemd() {
    info "Reloading systemd configuration"
    systemctl daemon-reload
    systemctl restart "getty@${KIOSK_TTY}.service" || true
    ok "Systemd reloaded"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Uninstall Functions
# ═══════════════════════════════════════════════════════════════════════════════

uninstall() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  UNINSTALLING KIOSK CONFIGURATION"
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""

    # Remove getty override
    local override_dir="/etc/systemd/system/getty@${KIOSK_TTY}.service.d"
    if [[ -d "$override_dir" ]]; then
        rm -rf "$override_dir"
        info "Removed: $override_dir"
    fi

    # Remove auto-start from .bash_profile
    local bash_profile="/home/$KIOSK_USER/.bash_profile"
    if [[ -f "$bash_profile" ]]; then
        # Check if it's our generated file
        if grep -q "Generated by setup_kiosk.sh" "$bash_profile"; then
            rm "$bash_profile"
            info "Removed: $bash_profile"
        else
            warn "Keeping $bash_profile (not generated by this script)"
        fi
    fi

    # Reload systemd
    systemctl daemon-reload

    ok "Uninstall complete"
    echo ""
    echo "Note: Installation directory $INSTALL_DIR was NOT removed."
    echo "      Backups are still in /home/$KIOSK_USER/.kiosk-backup-*"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

show_usage() {
    echo "Usage: $0 [check|install|uninstall] [-y]"
    echo ""
    echo "Commands:"
    echo "  check      Check for existing auto-start configurations"
    echo "  install    Install kiosk auto-start for calendar console"
    echo "  uninstall  Remove kiosk configuration (keeps backups)"
    echo ""
    echo "Options:"
    echo "  -y, --yes  Skip confirmation prompts"
    echo ""
    echo "Configuration (via .env or environment):"
    echo "  KIOSK_USER   Username for kiosk (default: kiosk)"
    echo "  KIOSK_TTY    TTY device (default: tty1)"
    echo "  INSTALL_DIR  Installation directory (default: /home/\$KIOSK_USER/ha-calendar)"
    echo ""
}

main() {
    local cmd=""
    local skip_confirm=false

    # Parse arguments
    for arg in "$@"; do
        case "$arg" in
            -y|--yes)
                skip_confirm=true
                ;;
            check|install|uninstall)
                cmd="$arg"
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                echo "Unknown option: $arg"
                show_usage
                exit 1
                ;;
        esac
    done

    # Default command
    cmd="${cmd:-check}"

    echo ""
    echo "╔═══════════════════════════════════════════════════════════════════╗"
    echo "║         HA CALENDAR CONSOLE - KIOSK SETUP                        ║"
    echo "╚═══════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "  Kiosk User: $KIOSK_USER"
    echo "  Target TTY: $KIOSK_TTY"
    echo "  Install Dir: $INSTALL_DIR"
    echo ""

    case "$cmd" in
        check)
            detect_existing_autostart
            ;;
        install)
            check_root
            detect_existing_autostart

            if [[ "$skip_confirm" == "true" ]]; then
                echo ""
                info "Proceeding with installation (-y flag)"
            else
                echo ""
                read -p "Proceed with installation? [y/N] " -n 1 -r
                echo ""
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    info "Installation cancelled"
                    exit 0
                fi
            fi

            backup_existing
            install_calendar_files
            setup_autologin
            setup_autostart
            reload_systemd
            echo ""
            ok "Installation complete!"
            echo ""
            echo "  The calendar console will start automatically on next login to $KIOSK_TTY"
            echo "  To test now, switch to $KIOSK_TTY (Alt+F1) or reboot"
            echo ""
            ;;
        uninstall)
            check_root
            uninstall
            ;;
    esac
}

main "$@"
