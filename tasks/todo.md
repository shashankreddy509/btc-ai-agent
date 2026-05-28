# Todo
Current task planning goes here. Each session creates a new section.

---

## Template
**Goal**: [what we're building]

### Plan

### Review
- Result: [what was done]
- Tests: [passed/failed]
- Notes: [anything notable]

---

## Backlog (future improvements)

### Trading / Signal Quality
- [x] **Opposing position guard per TF**: Implemented — `_execute_entry` checks `open_positions` for opposite direction; skip or flip based on `opposite_signal_action` setting. (`scanner.py:763–774`)
- [x] **Signal survival across restarts**: Implemented — `_load_state` restores pending signals, open positions, and history from Firestore on startup. (`scanner.py:1250`)

### Notifications & Monitoring
- [x] **Telegram notifications**: Per-user trade alerts implemented. `telegram_chat_id` in user settings → personal alerts on position open, TP, SL. Uses app bot token. (`notifiers.py`, `scanner.py`, `app.py`, `index.html`, `main.js`)
- [x] **Scanner crash watchdog**: Fixed — `_Scanner.thread` stores thread ref; `get_state()` calls `thread.is_alive()` and resets `running=False` + clears Firestore if dead. (`scanner.py`)

---

## Security Backlog (audit: 2026-04-28)

### Critical
- [x] **Unauthenticated scan/brief trigger endpoints**: Fixed — added `Depends(_require_admin)` to both routes. (`app.py:399,419`)

### High
- [x] **No allowlist on user settings write**: Fixed — `_USER_SETTING_KEYS` allowlist applied to `PUT /api/settings/user`. (`app.py`)
- [x] **No allowlist on app settings write**: Fixed — `_APP_SETTING_KEYS` allowlist applied to `PUT /api/settings/app`. (`app.py`)
- [x] **XSS via raw innerHTML**: Fixed — added `esc()` helper; wrapped `h.pattern`, `r.leverage`, `r.date`, `r.predicted_regime`, `r.actual_regime` in all `innerHTML` templates. (`main.js`)
- [x] **Admin email hardcoded as fallback**: Fixed — removed hardcoded default from `config.py`; startup warns if neither `FIREBASE_OWNER_UID` nor `FIREBASE_ADMIN_EMAIL` is set. (`config.py`, `app.py`)
- [x] **No rate limiting**: Fixed — `_RateLimitMiddleware` added; 60 req/min per IP on public `/api/` endpoints; auth-gated routes exempt. (`app.py`)

### Medium
- [x] **Any auth'd user can read app secrets**: Fixed — added `Depends(_require_admin)` to `GET /api/settings/app`. (`app.py:709`)
- [x] **`qty` validator accepts floats, no upper bound**: Fixed — `isinstance(qty, int)` check + `<= 1000` upper bound. (`app.py`)
- [x] **Startup exception uses `print()` not Rich**: Fixed — all `print()` replaced with `console.print()`. (`app.py`)
- [x] **No security response headers**: Fixed — `_SecurityHeadersMiddleware` adds `X-Frame-Options`, `X-Content-Type-Options`, `HSTS`, `CSP`. (`app.py`)

### Low
- [x] **`serviceAccountKey.json` at project root**: Fixed — startup warns if file exists at project root, advises using `FIREBASE_SERVICE_ACCOUNT` env var. (`app.py`)
- [x] **No guard on empty Firebase web config**: Fixed — startup warns if any of `FIREBASE_WEB_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, `FIREBASE_APP_ID` are blank. (`app.py`)
