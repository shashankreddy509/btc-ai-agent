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

## EC2 slowdown — split Playwright collector to own capped service (2026-05-29)
**Goal**: EC2 (t3.medium, 2 vCPU) goes slow intermittently. Root cause: liquidity collector runs headless Chromium **in the web process** every 15 min; multi-process Chromium grabs both vCPUs for 60-90s (worse on `networkidle` stalls) → uvicorn + 1-min scanner starve → API crawls.

### Review
- Result: Split collector out of the web process into its own cgroup-bounded systemd unit.
  - `collector.py`: `INTERVAL_SECONDS` now env-tunable via `LIQUIDITY_INTERVAL_MIN` (default 15, unchanged).
  - `deploy/install_service.sh`: writes 2 units — `btc-agent` (web+scheduler, `Environment=LIQUIDITY_ENABLED=false` so it never spawns the in-process collector) and new `btc-liquidity` (`uv run liquidity-collect`, `CPUQuota=60%` + `MemoryMax=900M` + `Nice=15` + `IOSchedulingClass=idle`, `LIQUIDITY_INTERVAL_MIN=30`). Also runs `playwright install chromium`.
  - `deploy/deploy.sh`: restarts `btc-liquidity` too when the unit exists.
- Tests: py_compile + `bash -n` pass; interval parse verified (unset→900, =30→1800).
- Deploy: `./deploy/deploy.sh <host>` then **on EC2 once**: `bash deploy/install_service.sh` (creates the new unit). Verify CloudWatch CPU smooths + `journalctl -u btc-liquidity -f`.
- Flagged (not fixed): `login()`/`load_chart` use `wait_until="networkidle"` on CoinGlass — main stall risk; switching to `domcontentloaded` + explicit selector wait would cut the worst CPU bursts. Touches scrape correctness → left for decision.

---

## 4-Flag multi-fire fix (2026-05-29)
**Goal**: One visual 4-Flag fired 5 same-TF shorts (62m). Stop the cluster.

### Review
- Result: Two layers in `scanner.py`. Layer 1 (`_scan_patterns`): dropped rolling `for w in range(len(bars)-3)` window scan; 4-Flag now detects only the just-closed window `bars[-4:]` (mirrors Engulfing) → no overlapping-window cluster. Layer 2 (`_execute_entry`): added same-(TF, direction) open-position guard after the flip/skip block, before `max_concurrent` cap → max one position per TF/dir; flip unaffected (closes opposite first).
- Tests: 151 passed. Added `TestFourFlagLatestWindow` (latest-window-only) + `TestSameTfDirectionGuard` (block / different-tf-allowed / flip-still-works).
- Notes: Guard is `(tf, direction)` not pattern-scoped — also blocks BSG+4-Flag same-dir/TF double exposure (deliberate). Root cause: distinct `bar_open_time` per overlapping window slipped past `_is_duplicate`.

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
