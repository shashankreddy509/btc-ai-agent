# Firebase / Firestore Patterns

## Collections
| Collection | Key | Contents |
|-----------|-----|---------|
| `app_settings/config` | fixed doc | All app-level settings (Anthropic, Scanner, Trading config) |
| `user_settings/{uid}` | Firebase UID | Coinbase API credentials (user-specific) |
| `trading_signals/{id}` | signal UUID | One doc per signal; status: pending→triggered/skipped/expired |
| `trading_positions/{signal_id}` | signal UUID | One doc per position; upserted on every state change |
| `trading_history/{id}_{suffix}` | signal_id + reason | One doc per close event |

## Write Rules
- All writes are fire-and-forget background threads (`_bg()`) — never await or block
- Use `merge=True` (set with merge) for settings updates to avoid overwriting unrelated fields
- Only write on meaningful events, NOT on every 5-second tick

## Read Rules
- `load_state()` / `load_app_settings()` / `load_user_prefs()` are synchronous — called once at startup only
- Firestore unavailability is non-fatal — log warning, fall back to `.env` values

## Auth
- Backend uses Firebase Admin SDK (`firebase_admin`) initialized via `get_firebase_app()` (lru_cache)
- Credentials: `serviceAccountKey.json` (project root) or `FIREBASE_SERVICE_ACCOUNT` env var
- Frontend uses Firebase JS SDK compat v10 (CDN loaded)
- Token verification: `fb_auth.verify_id_token(creds.credentials)` in `verify_token` dependency

## Settings Hierarchy (precedence: high → low)
1. Firestore `app_settings/config` (loaded at startup + on save)
2. Firestore `user_settings/{FIREBASE_OWNER_UID}` (Coinbase keys)
3. `.env` file (fallback defaults)

## Sensitive Field Masking
- Masked in GET responses: `anthropic_api_key`, `telegram_bot_token`, `email_pass`, `coinbase_api_key`, `coinbase_api_secret`
- `apply_settings()` skips any value containing `****` — safe to pass GET response back to PUT
