# BTC AI Agent

A BTC-focused trading intelligence system that scans for candlestick patterns across perpetual futures timeframes, generates AI morning briefings, and manages paper/live positions via Coinbase Advanced Trade.

## Features

- **Pattern Scanner** — detects 4-Flag, Morning Star, Evening Star, Bullish/Bearish Engulfing across all minute-based timeframes from 30 m to 1440 m, cross-checked against DEPO price levels
- **Morning Briefing** — fetches RSS + Reddit news, summarizes with Claude AI, delivers to Telegram/email/terminal
- **Trading Scanner** — signal generation from pattern hits → entry trigger → position management with stop-loss and take-profit
- **Web Dashboard** — FastAPI dashboard showing live scan results, briefing, and trading activity
- **Coinbase Execution** — market and stop-limit orders via Coinbase Advanced Trade REST API (paper + live modes)
- **EC2 Deployment** — systemd service with scheduler + web server running together

---

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

---

## Installation

```bash
git clone <repo-url>
cd btc-ai-agent
uv sync
cp .env.example .env
# edit .env with your API keys
```

---

## Configuration (`.env`)

| Variable | Description | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API key (required for briefings) | — |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | — |
| `TELEGRAM_CHAT_ID` | Telegram chat/group ID | — |
| `EMAIL_SMTP_HOST` | SMTP server hostname | — |
| `EMAIL_SMTP_PORT` | SMTP port (e.g. 465 for SSL) | 465 |
| `EMAIL_SMTP_USER` | SMTP username | — |
| `EMAIL_SMTP_PASS` | SMTP password | — |
| `EMAIL_TO` | Recipient email address | — |
| `BRIEFING_TIME` | Daily briefing time in UTC (HH:MM) | `07:30` |
| `SCANNER_TIME` | Daily scan time in UTC (HH:MM) | `08:00` |
| `SCANNER_INTERVAL_MIN` | If set, runs scanner every N minutes instead of daily | — |
| `SCANNER_TF_MIN` | Minimum timeframe to scan (minutes) | `30` |
| `SCANNER_TF_MAX` | Maximum timeframe to scan (minutes) | `1440` |
| `SCANNER_PATTERNS` | Comma-separated patterns to detect | `4-Flag,Morning Star,Evening Star,Bullish Engulfing,Bearish Engulfing` |
| `DELIVERY_CHANNELS` | Comma-separated: `terminal,telegram,email,desktop` | `terminal` |
| `COINBASE_API_KEY` | Coinbase Advanced Trade API key | — |
| `COINBASE_API_SECRET` | Coinbase Advanced Trade API secret | — |
| `COINBASE_PRODUCT_ID` | Product to trade (e.g. `BTC-USD`) | `BTC-USD` |

---

## Usage

```bash
# Run morning briefing immediately
uv run python main.py brief

# Run pattern scan immediately
uv run python main.py scan

# Run trading scanner (paper/live mode set in dashboard or .env)
uv run python main.py trade

# Start scheduler daemon (briefing + scanner on schedule)
uv run python main.py run

# Start web dashboard only
uv run python main.py web

# Start scheduler + web dashboard together (for EC2)
uv run python main.py all --host 0.0.0.0 --port 8000
```

The web dashboard runs at `http://localhost:8000` by default.

---

## Pattern Detection

| Pattern | Bars Required | Description |
|---|---|---|
| 4-Flag | 4 | Alternating green/red candles, tight consolidation range |
| Morning Star | 3 | Bearish → doji star → bullish reversal |
| Evening Star | 3 | Bullish → doji star → bearish reversal |
| Bullish Engulfing | 2 | Bullish candle fully engulfs prior bearish candle |
| Bearish Engulfing | 2 | Bearish candle fully engulfs prior bullish candle |

### DEPO Levels

Fixed price grid starting at 126,208 and stepping down by 1,700 (48 levels total down to ~45,000). A pattern hit is flagged when any candle in the pattern touches a DEPO level.

---

## Data Source

Candles are fetched from **Binance USDT-M Futures** (`fapi.binance.com`) with automatic fallback to **Bybit** if geo-blocked. The symbol is `BTC/USDT:USDT` (perpetual contract).

---

## EC2 Deployment

```bash
# Deploy code
./deploy/deploy.sh

# Install systemd service (run on EC2)
./deploy/install_service.sh
```

The service runs `python main.py all --host 0.0.0.0 --port 8000` and auto-restarts on failure.

---

## Running Tests

```bash
uv run pytest tests/ -v
```

---

## Project Structure

```
btc-ai-agent/
├── main.py                    # CLI entrypoint
├── btc_agent/
│   ├── config.py              # Settings loaded from .env
│   ├── notifiers.py           # Terminal, Telegram, email delivery
│   ├── storage.py             # JSON persistence helpers
│   ├── scheduler.py           # Schedule-based daemon
│   ├── briefing/              # AI morning briefing (RSS + Claude)
│   ├── scanner/               # Pattern scanner (data, aggregator, patterns, depo)
│   ├── trading/               # Trading scanner, position manager, Coinbase executor
│   └── web/                   # FastAPI dashboard
├── tests/                     # Unit tests
├── data/                      # Runtime JSON state (gitignored)
└── deploy/                    # EC2 deployment scripts
```
