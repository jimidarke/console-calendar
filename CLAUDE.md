# CLAUDE.md

Guidance for Claude Code working in this repository. See `README.md` for user-facing docs (setup, env vars, controls, deploy).

## Repo shape

Two components, one repo:

- **Console TUI** — `ha_calendar_console.py` plus helpers (`ha_list_calendars.py`, `test_ha_calendar.py`). Single-file curses app, **stdlib-only**. Loads config from `.env` via the shared `cc_env.load_env`.
- **cal-quickadd** — `cal-quickadd/app/` (FastAPI + Gemini + Google Calendar). Has its own `requirements.txt` and Docker build.

They are functionally independent (no Python imports between them). The integration point is HTTP: TUI calls `CAL_QUICKADD_URL/add` on `F2` and polls `CAL_QUICKADD_URL/health` for the status pill.

## Key files

- `cc_env.py` — shared `.env` loader. Used by all four scripts that need env loading. Stdlib-only so the TUI keeps zero deps. **Do not** reintroduce `python-dotenv` for that reason.
- `ha_calendar_console.py:189-` — `HACalendarClient._make_request`. 401/403/404 produce specific user-facing error messages; the back-off logic in `get_events` (always advance `last_fetch`) prevents tight-loop hammering of HA when fetches fail. Keep both behaviours intact.
- `cal-quickadd/app/ai_parser.py` — `_call_gemini` is the one place Gemini is called. It handles retry/backoff/fallback and raises `QuotaExceeded` when both models are exhausted. Don't add direct `model.generate_content` calls elsewhere.
- `cal-quickadd/app/main.py` — `/add` and `/scan` translate `QuotaExceeded` to **HTTP 429 + Retry-After** (not 422). `/health` must NOT include `last_event` PII.
- `deploy/mserver/` — TUI bare-metal kiosk (systemd unit + sync bootstrap). `deploy/nserver/` — cal-quickadd Docker (build context = repo root so `cc_env.py` is bundled). The legacy `cal-quickadd/Dockerfile` and `cal-quickadd/docker-compose.yml` are still present but unused; remove them once you're confident no external script depends on them.

## Production topology

- **mserver** runs the TUI bare-metal on tty1 as `displayuser` (autologin via `agetty`). Files at `/home/displayuser/ha-calendar/`. The TUI is **not** in a container — it needs the TTY for curses kiosk display.
- **nserver** runs `cal-quickadd` as a Docker container on port 8419, fronted by an existing nginx-proxy + DNS. Files at `/root/docker/console-calendar/` (or wherever you sync the repo). The OAuth consent app is in Testing mode, so refresh tokens expire every 7 days — the `/health` `oauth.state` field and the TUI pill surface this proactively.

## Testing

- `cal-quickadd/test_parser_retry.py` — unit tests for retry/backoff/fallback. All Gemini calls mocked. Run with any dummy `GEMINI_API_KEY=test`.
- `cal-quickadd/test_api.py` — FastAPI integration tests. Some hit real Gemini; the quota-propagation and health tests mock the parser.
- TUI has no automated tests beyond `test_ha_calendar.py` (HA connectivity smoke test).

## Conventions

- Single source of version info: `VERSION.txt` for now (TODO: migrate to `pyproject.toml` if a packaging story is added).
- Don't import between the two components. If shared logic emerges beyond `cc_env.py`, add another small stdlib-only module at the repo root.
- TUI code paths must remain stdlib-only.
