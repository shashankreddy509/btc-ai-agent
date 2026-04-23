# Python Style Rules

## Error Handling
- Never use bare `except:` — always `except Exception as e:` or specific exception type
- Log errors with `console.print(f"[yellow]...: {e}[/yellow]")` using Rich, not `print()`
- Don't swallow errors silently — always log them even in fire-and-forget threads

## Firestore / Threading
- All Firestore writes MUST use the `_bg()` fire-and-forget helper — never block the scan loop
- Never call `_get_db()` on the main thread during the 5-second tick loop

## Config
- Read config values from `btc_agent.config` module-level vars
- To override at runtime, call `config.apply_settings(d)` — never set `config.X = Y` directly from routes
- `apply_settings` skips masked values (containing `****`) automatically

## Imports
- Lazy imports inside functions for heavy modules (firebase_admin, trading scanner) to avoid circular imports and slow startup
- `from __future__ import annotations` at top of files with complex type hints

## Type Hints
- Use `dict | None` and `list[X]` style (Python 3.10+ union syntax)
- Return type hints on public functions; skip on private `_` functions if obvious

## Functions
- Private helpers prefixed with `_`
- Keep trading loop functions pure where possible — side effects only at entry/exit points
- Max function length ~50 lines; split if longer and complexity warrants it
