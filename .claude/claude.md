# BTC AI Agent — Claude Code Rules

## Project Overview
Python FastAPI web app for Bitcoin trading analysis and automated live trading.
- **Stack**: Python 3.12, FastAPI, Firebase/Firestore, Coinbase Advanced Trade API, Anthropic Claude
- **Modules**: `btc_agent/briefing` · `btc_agent/scanner` · `btc_agent/trading` · `btc_agent/web`
- **Auth**: Firebase Auth (Google sign-in), bearer token verified server-side via `verify_token`
- **Storage**: Firestore — `app_settings/config` (app-level), `user_settings/{uid}` (user-level), `trading_*` collections
- **Deploy**: EC2 ap-south-1, Nginx → port 8000, domain `btc.gshashank.com`
- **Admin email**: `shashankreddy509@gmail.com` (admin-only UI sections gated by this)

## Key Commands
```bash
# Tests
.venv/bin/python -m pytest tests/ -v --tb=short

# Dev server
uv run uvicorn btc_agent.web.app:app --reload --port 8000

# Syntax check
python3 -m py_compile btc_agent/trading/scanner.py btc_agent/web/app.py btc_agent/config.py

# Deploy
./deploy/deploy.sh
```

## Key Files
| File | Purpose |
|------|---------|
| `btc_agent/config.py` | All config vars + `apply_settings(d)` to override from Firestore |
| `btc_agent/trading/scanner.py` | Main trading loop, signal detection, position management |
| `btc_agent/trading/firestore_store.py` | Firestore R/W: `save/load_app_settings`, `save/load_user_prefs`, trade events |
| `btc_agent/trading/executor.py` | Coinbase REST client, JWT auth, order placement |
| `btc_agent/web/app.py` | FastAPI: `pub` router (public), `priv` (trading), `priv_cfg` (settings) |
| `btc_agent/web/auth.py` | `verify_token` dependency — Firebase ID token verification |
| `btc_agent/web/static/main.js` | SPA frontend: auth, trading dashboard, settings, scanner |
| `btc_agent/web/templates/index.html` | Single-page shell with sidebar + 4 pages |

## Workflow Orchestration

### 1. Plan Mode Default
- Enter Plan mode for ANY non-trivial task (3+ steps or architectural decisions).
- If something goes sideways, STOP and re-plan — don't keep pushing.
- Write detailed specs upfront to reduce ambiguity.

### 2. Subagent Strategy
- Use Explore agent for codebase searches to keep main context clean.
- Offload parallel analysis to subagents.
- For complex problems, throw more compute at it via subagents.

### 3. Self-Improvement
- After ANY correction: update `tasks/lesson.md` with the pattern.
- Write rules that prevent the same mistake.
- Review lessons at session start.

### 4. Verification Before Done
- Never mark a task complete without proving it works.
- Run `pytest` after any change touching trading logic or config.
- Ask: "Would a staff engineer approve this?"

### 5. Demand Elegance
- For non-trivial changes: ask "Is there a more elegant way?"
- Skip for simple, obvious fixes — don't over-engineer.

### 6. Autonomous Bug Fixing
- When given a bug report: fix it, don't ask for hand-holding.
- Point at logs, errors, failing tests — then resolve them.

## Code Style
- **No bare `except:`** — always catch specific exceptions or `Exception as e`
- **Firestore writes** — always fire-and-forget via `_bg()` helper, never block the scan loop
- **Config overrides** — use `config.apply_settings(d)`, not direct attribute assignment
- **Router split** — trading routes → `priv`, settings routes → `priv_cfg`, public → `pub`
- **Admin gate** — UI admin sections check `_currentUser?.email === 'shashankreddy509@gmail.com'`
- **No comments** for obvious code — only comment non-obvious constraints or workarounds
- **Type hints** — use where clarity is added, not mandatory everywhere

## Task Management
1. **Plan First**: Write plan to `tasks/todo.md` with checkable items.
2. **Verify Plan**: Check in before starting implementation.
3. **Track Progress**: Mark items complete as you go.
4. **Explain Changes**: High-level summary at each step.
5. **Capture Lessons**: Update `tasks/lesson.md` for any correction.

## Core Principles
- **Simplicity First**: Make every change as simple as possible. Minimal code impact.
- **No Laziness**: Find root cause. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
