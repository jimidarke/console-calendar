# Security Audit: cal-quickadd

> Audit date: 2026-04-08
> Scope: Full scan of all project files
> Status: Documented — no hardcoded secrets found

---

## HIGH

### H1. CORS wildcard allows any origin
- **File:** `app/main.py:19`
- **Code:** `allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]`
- **Impact:** Any website can make requests to this API from a user's browser, enabling cross-origin event creation and Gemini credit abuse.
- **Fix:** Restrict `allow_origins` to the actual frontend host(s), e.g. `["http://192.168.1.45:8419"]`.

### H2. No authentication on any endpoint
- **File:** `app/main.py:76, 128, 185`
- **Impact:** `/add`, `/scan`, and `/health` are completely open. Anyone on the network can create arbitrary calendar events, consume Gemini API credits, and read config data.
- **Fix:** Add API key header check (e.g. `X-API-Key` validated against an env var) or use a reverse proxy with auth.

### H3. /health endpoint leaks PII
- **File:** `app/main.py:185-192`
- **Impact:** Exposes family member names, timezone, and full last-created event data to unauthenticated callers.
- **Fix:** Gate behind auth, or return only `{"status": "ok"}` for anonymous requests.

### H4. Raw exception messages returned to clients
- **File:** `app/main.py:87, 115, 143`
- **Code:** `raise HTTPException(status_code=422, detail=f"Could not parse input: {e}")`
- **Impact:** Internal Python exception details (paths, library names, API errors) leak to callers.
- **Fix:** Log full exception server-side, return generic error messages to clients.

---

## MEDIUM

### M1. No max length on text input
- **File:** `app/main.py:58`
- **Impact:** Unbounded text can be sent to Gemini, causing high API costs or timeouts.
- **Fix:** Add `text: str = Field(..., max_length=1000)` to `AddRequest`.

### M2. Full image buffered before size check
- **File:** `app/main.py:135-137`
- **Impact:** Entire upload is read into memory before the 10MB limit is enforced. Large uploads can cause memory pressure.
- **Fix:** Check `Content-Length` header before reading, or configure uvicorn/nginx body size limits.

### M3. MIME type check trusts client header
- **File:** `app/main.py:132-133`
- **Impact:** `file.content_type` is client-controlled and trivially spoofable. Non-image files can bypass validation.
- **Fix:** Validate file magic bytes (JPEG FFD8, PNG 89504E47) instead of the Content-Type header.

### M4. Rate limiter trusts raw X-Forwarded-For
- **File:** `app/main.py:36`
- **Impact:** Attackers can bypass rate limiting by sending arbitrary `X-Forwarded-For` headers per request.
- **Fix:** Ignore `X-Forwarded-For` unless behind a trusted reverse proxy. If proxied, use only the last hop.

### M5. In-memory rate limiter grows unboundedly
- **File:** `app/main.py:25-26`
- **Impact:** `_rate_limit` dict stores keys per IP forever — timestamps are pruned but IP entries are never evicted. Spoofed IPs cause unbounded memory growth.
- **Fix:** Periodically evict stale entries, or use an LRU-bounded dict.

### M6. Rate limiting only on POST requests
- **File:** `app/main.py:41`
- **Impact:** GET endpoints (including `/health` with PII) can be hit at unlimited rate.
- **Fix:** Apply rate limiting to all endpoints, or at minimum to `/health`.

### M7. Client MIME type passed to Gemini API
- **File:** `app/ai_parser.py:128`, `app/main.py:140`
- **Impact:** User-supplied `content_type` is forwarded directly to Gemini. Low exploitability but violates input trust boundary.
- **Fix:** Derive MIME type from file magic bytes rather than the client header.

### M8. Service binds 0.0.0.0 with no auth
- **File:** `Dockerfile:12`, `docker-compose.yml`
- **Impact:** Service is accessible on all network interfaces. Combined with no auth (H2), the entire LAN can interact with it.
- **Fix:** Bind to `127.0.0.1` if local-only, or use `127.0.0.1:8419:8419` in docker-compose port mapping. Use a reverse proxy with auth for LAN access.

---

## LOW

### L1. OAuth token written with default permissions
- **File:** `app/calendar_api.py:37`, `setup_oauth.py:37`
- **Impact:** Google OAuth refresh token may be world-readable depending on umask.
- **Fix:** Add `token_path.chmod(0o600)` after writing.

### L2. Gemini responses logged at INFO level
- **File:** `app/ai_parser.py:102, 139`
- **Impact:** Full AI responses (which may contain parsed PII) appear in INFO-level logs.
- **Fix:** Log at DEBUG level, or truncate/redact sensitive fields.

### L3. User-Agent logged
- **File:** `app/main.py:38`
- **Impact:** User-Agent strings containing device fingerprint info are logged. Low risk for home-lab.

### L4. No HTTPS enforcement
- **File:** `Dockerfile:12`
- **Impact:** Traffic is unencrypted on the network. API keys and tokens in transit are visible.
- **Fix:** Use a reverse proxy (nginx, caddy) with TLS termination.

### L5. Service worker pass-through
- **File:** `app/static/sw.js:4`
- **Impact:** SW intercepts all fetches but just forwards them. Benign — exists for PWA installability.

---

## Positives

- No hardcoded secrets — all credentials loaded from environment variables
- `.env` and `config/` properly gitignored
- No SQL, command injection, or path traversal surfaces
- No dangerous deserialization (`json.loads` only)
- No SSRF — no user-controlled outbound URLs
- Frontend uses `escapeHtml()` for rendering user-controlled data
- Image upload has a 10MB size cap (enforced, though after buffering)
- Empty text input is validated before processing

---

## Priority Remediation Order

1. Add endpoint authentication (H2) — single most impactful fix
2. Restrict CORS origins (H1)
3. Sanitize error responses (H4)
4. Strip PII from /health or gate behind auth (H3)
5. Add text input max_length (M1)
6. Fix rate limiter trust boundary (M4, M5)
7. Enforce body size before buffering (M2)
