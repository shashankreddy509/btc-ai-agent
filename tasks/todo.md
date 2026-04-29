# Todo
Current task planning goes here. Each session creates a new section.

---

## Template
**Goal**: [what we're building]

### Plan
- [ ] To implement some more strategies under a new section. I will upload the PDF for the strategy details. Under strategies folder

### Review
- Result: [what was done]
- Tests: [passed/failed]
- Notes: [anything notable]

---

## Backlog (future improvements)

### Trading / Signal Quality
- [ ] **Opposing position guard per TF**: Long and short on the same TF can both be open simultaneously. Skip new signal if opposite-direction position already open on same TF. Deferred for now.
- [ ] **Backtesting mode**: Replay historical 1m bars through `_scan_patterns` and record signal → outcome. Needed before trusting new patterns live.
- [ ] **Signal survival across restarts**: Pending in-memory signals lost on server restart. Re-discovered on next bar, but a trigger can be missed in that window.

### Notifications & Monitoring
- [ ] **Telegram notifications**: `telegram_bot_token` in settings is not wired up. Alert on: signal triggered, position opened, TP/SL hit, scanner crash.
- [ ] **Scanner crash watchdog**: If background scanner thread dies, UI still shows "running". Detect dead thread and notify user or auto-restart.

### Dashboard / UX
- [ ] **PnL dashboard**: Trade history in Firestore but no UI summary — total realized PnL, win rate per pattern, average RR.
- [ ] **Recent trades pagination**: Recent trades table needs pagination to show all trades beyond the current visible limit.

### Brokers
- [ ] **Pepperstone (cTrader)**: Plan written, implementation paused. Needs `ctrader_open_api` SDK, `PepperstoneAdapter`, UI credential fields.
- [ ] **XM, Vantage**: MT4/MT5 only — would require MetaApi cloud bridge. Revisit later.

---

## Security Backlog (audit: 2026-04-28)

### Critical
- [ ] **Unauthenticated scan/brief trigger endpoints**: `POST /api/scan/trigger` and `POST /api/brief/trigger` are public — no auth. Anyone can spam and exhaust Anthropic API quota. Move to `priv` or add `Depends(_require_admin)`. (`app.py:164–201`)

### High
- [ ] **No allowlist on user settings write**: `PUT /api/settings/user` accepts arbitrary keys → Firestore. Apply same `setting_keys` allowlist used in `POST /api/trading/settings`. (`app.py:363–370`)
- [ ] **No allowlist on app settings write**: Same issue on `PUT /api/settings/app`. (`app.py:346–353`)
- [ ] **XSS via raw innerHTML**: `signal_id`, `pattern`, `tf` from server JSON injected into `innerHTML` with no escaping. Add `esc()` helper or use `el.textContent`. (`main.js:645,842,890`)
- [ ] **Admin email hardcoded as fallback**: `FIREBASE_ADMIN_EMAIL` defaults to hardcoded email in `config.py`. Always set `FIREBASE_OWNER_UID` in prod; add startup assertion if missing. (`config.py:60`)
- [ ] **No rate limiting**: No rate limiting at app or Nginx level. Add `slowapi` to `pub` endpoints + `limit_req_zone` in Nginx config.

### Medium
- [ ] **Any auth'd user can read app secrets**: `GET /api/settings/app` is auth-required but not admin-only — leaks masked (but partially revealing) API keys. Add `Depends(_require_admin)`. (`app.py:339–343`)
- [ ] **`qty` validator accepts floats, no upper bound**: `int(2.0) == 2.0` passes. Fix: `isinstance(qty, int)` + upper bound (e.g. 1000). (`app.py:72–78`)
- [ ] **Startup exception uses `print()` not Rich**: Leaks exception detail to raw stdout/system logs. Replace with `console.print()`. (`app.py:110`)
- [ ] **No security response headers**: Missing `X-Frame-Options`, `X-Content-Type-Options`, `CSP`, `HSTS`. Add `SecurityHeadersMiddleware` in `app.py`.

### Low
- [ ] **`serviceAccountKey.json` at project root**: Nginx misconfiguration could expose it. Use `FIREBASE_SERVICE_ACCOUNT` env var in production. (`firebase_app.py:12`)
- [ ] **No guard on empty Firebase web config**: Blank env vars cause silent JS SDK failure. Add startup warning. (`app.py:130–139`)
