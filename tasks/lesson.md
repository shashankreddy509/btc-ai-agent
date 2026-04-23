# Lessons Learned

Track patterns from corrections to avoid repeating mistakes.

---

## Lesson: 4-Flag Trigger Price Uses Body High, Not Wick
**Context**: `_bars_to_signal` was using last bar body instead of pattern high/low for entry trigger.
**Fix**: Use `max(bar["body_hi"] for bar in flag_bars)` across all 4 flag bars.
**Rule**: Pattern trigger price must span the full pattern, not just the last bar.

## Lesson: calc_sl Always Uses Wick
**Context**: calc_sl was refactored to always use wick as stop-loss, not body.
**Rule**: SL is always wick-based. Body-based SL is no longer a code path.

## Lesson: EC2 Private Key Newline Mangling
**Context**: `.env` on EC2 stored PEM key with literal `\n` stripped to just `n` chars.
**Fix**: `_normalize_pem()` handles 3 storage formats: real newlines, `\\n`, and `n`-separated.
**Rule**: Never assume PEM key format from env var — always normalize through `_normalize_pem()`.

## Lesson: Firebase Auth Domain Must Match Exactly
**Context**: App accessed at `127.0.0.1:8000` — Firebase only pre-authorizes `localhost`, not `127.0.0.1`.
**Rule**: Always access dev server at `localhost:8000`, never `127.0.0.1:8000`.
