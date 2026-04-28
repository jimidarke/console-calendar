"""Shared .env loader. Stdlib-only so the TUI keeps zero runtime dependencies.

Used by:
- ha_calendar_console.py (TUI)
- ha_list_calendars.py
- test_ha_calendar.py
- cal-quickadd/app/config.py (replaces python-dotenv)

Behaviour:
- Searches the given start dir then walks parents, stopping at the first .env found.
- Existing process env vars take precedence (mirrors python-dotenv default).
- Lines starting with '#' or blank are ignored. Surrounding quotes are stripped.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env(start: str | os.PathLike[str] | None = None, *, max_parents: int = 4) -> Path | None:
    """Find and load a .env file. Returns the path loaded, or None if none found."""
    start_path = Path(start) if start else Path.cwd()
    if start_path.is_file():
        start_path = start_path.parent

    candidate: Path | None = None
    here = start_path.resolve()
    for _ in range(max_parents + 1):
        probe = here / ".env"
        if probe.is_file():
            candidate = probe
            break
        if here.parent == here:
            break
        here = here.parent

    if candidate is None:
        return None

    for raw in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value

    return candidate
