# Graph Report - .  (2026-04-30)

## Corpus Check
- Corpus is ~31,766 words - fits in a single context window. You may not need a graph.

## Summary
- 663 nodes · 1296 edges · 25 communities detected
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 223 edges (avg confidence: 0.72)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Frontend SPA & UI|Frontend SPA & UI]]
- [[_COMMUNITY_Broker Adapter Layer|Broker Adapter Layer]]
- [[_COMMUNITY_Vishal Strategy Engine|Vishal Strategy Engine]]
- [[_COMMUNITY_Firebase & Firestore|Firebase & Firestore]]
- [[_COMMUNITY_Trading Models & Tests|Trading Models & Tests]]
- [[_COMMUNITY_Candlestick Pattern Detection|Candlestick Pattern Detection]]
- [[_COMMUNITY_Trading Scanner Core|Trading Scanner Core]]
- [[_COMMUNITY_Market Structure Levels|Market Structure Levels]]
- [[_COMMUNITY_Notifiers & Delivery|Notifiers & Delivery]]
- [[_COMMUNITY_OHLCV Aggregation|OHLCV Aggregation]]
- [[_COMMUNITY_Coinbase Executor & Tests|Coinbase Executor & Tests]]
- [[_COMMUNITY_Config Validation|Config Validation]]
- [[_COMMUNITY_Strategy Docs & Lessons|Strategy Docs & Lessons]]
- [[_COMMUNITY_Briefing Agent|Briefing Agent]]
- [[_COMMUNITY_Coinbase API Client|Coinbase API Client]]
- [[_COMMUNITY_Engulfing Patterns|Engulfing Patterns]]
- [[_COMMUNITY_Market Data Fetcher|Market Data Fetcher]]
- [[_COMMUNITY_Risk & Strategy Concepts|Risk & Strategy Concepts]]
- [[_COMMUNITY_4-Flag Pattern Logic|4-Flag Pattern Logic]]
- [[_COMMUNITY_App Config|App Config]]
- [[_COMMUNITY_Debug Tools|Debug Tools]]
- [[_COMMUNITY_Market Order Op|Market Order Op]]
- [[_COMMUNITY_Stop-Limit Order Op|Stop-Limit Order Op]]
- [[_COMMUNITY_Cancel Order Op|Cancel Order Op]]
- [[_COMMUNITY_Contract Size|Contract Size]]

## God Nodes (most connected - your core abstractions)
1. `_sc()` - 34 edges
2. `run_trading_scanner()` - 28 edges
3. `Signal` - 25 edges
4. `bar()` - 23 edges
5. `get_state()` - 22 edges
6. `bars()` - 22 edges
7. `fetchJSON()` - 21 edges
8. `Position` - 20 edges
9. `_ist()` - 19 edges
10. `aggregate_tf()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `Security Backlog` --references--> `Firebase Credential Externalization (Jinja2 Template Vars)`  [INFERRED]
  tasks/todo.md → btc_agent/web/app.py
- `Lesson: calc_sl Always Uses Wick` --conceptually_related_to--> `Chauke Zone Upper/Lower Line Entry Rules`  [INFERRED]
  tasks/lesson.md → strategies/4 Chauke pe Chauka Strategy PDF.pdf
- `Lesson: Firebase Auth Domain Must Match Exactly` --conceptually_related_to--> `Firebase Credential Externalization (Jinja2 Template Vars)`  [INFERRED]
  tasks/lesson.md → btc_agent/web/app.py
- `main()` --calls--> `run_scanner()`  [INFERRED]
  main.py → btc_agent/scanner/agent.py
- `main()` --calls--> `run_trading_scanner()`  [INFERRED]
  main.py → btc_agent/trading/scanner.py

## Hyperedges (group relationships)
- **All 6 Trading Strategies Share GTI Zone Infrastructure** — strategy_1_gti_zones, strategy_4_zone_entry_rules, strategy_5_sunday_weekly_entry, strategy_6_t1_t2_split, shared_gti_zone_infrastructure [EXTRACTED 0.95]
- **Ping Pong and Escalator Co-exist on Same Chart for Sideways vs Trending Regimes** — strategy_2_ping_pong, strategy_3_escalator, strategy_3_volatility_complement, strategy_2_session_zone [EXTRACTED 0.92]
- **Firebase Credential Remediation Spanning config.py, app.py, and Both HTML Templates** — web_app_firebase_remediation, index_html_firebase_config, login_html, index_html [EXTRACTED 1.00]

## Communities

### Community 0 - "Frontend SPA & UI"
Cohesion: 0.06
Nodes (63): _activateSubTab(), _adminSetMode(), _adminStopUser(), _applyHistFilters(), cancelPosition(), fetchJSON(), fmtPrice(), formatTs() (+55 more)

### Community 1 - "Broker Adapter Layer"
Cohesion: 0.05
Nodes (17): ABC, BrokerAdapter, BrokerAdapter, Return a human-readable account name from the broker API., Minimal interface every broker must implement., BinanceAdapter, Binance USDT-M Perpetual Futures via REST API., BybitAdapter (+9 more)

### Community 2 - "Vishal Strategy Engine"
Cohesion: 0.09
Nodes (20): _ist(), Unit tests for Vishal Sir strategy detection functions., _sc(), TestChaukepeChauka, TestDoubleProfit, TestEscalator, TestHighWinRate, TestPingPong (+12 more)

### Community 3 - "Firebase & Firestore"
Cohesion: 0.06
Nodes (44): get_firebase_app(), Shared Firebase Admin App — initialised once, reused by auth and Firestore modul, _bg(), _get_db(), load_app_settings(), load_state(), load_user_prefs(), Firestore persistence for trading state.  Collections:   trading_signals/{signal (+36 more)

### Community 4 - "Trading Models & Tests"
Cohesion: 0.1
Nodes (21): Tests for the trading scanner:   - detect_engulfing pattern   - calc_sl (wick of, Tests for _trail_sl() ratchet logic., TestCalcSL, TestQtyValidation, TestSignalExpiry, TestTrailSL, Position, Data models for the trading scanner. (+13 more)

### Community 5 - "Candlestick Pattern Detection"
Cohesion: 0.12
Nodes (15): detect_4flag(), detect_evening_star(), detect_morning_star(), Bearish 3-candle reversal:       Bar 0: large bullish candle       Bar 1: small, 4 Flags Whale Pattern — matches the Pine Script logic exactly:      1. Alternati, Bullish 3-candle reversal:       Bar 0: large bearish candle       Bar 1: small, bar(), bars() (+7 more)

### Community 6 - "Trading Scanner Core"
Cohesion: 0.16
Nodes (37): _active_patterns(), _bars_to_signal(), _bias_filter_enabled(), _build_broker(), _calc_tp(), _check_retracement(), _clear_on_stop(), _close_position() (+29 more)

### Community 7 - "Market Structure Levels"
Cohesion: 0.1
Nodes (34): compute_levels(), Market structure levels for the trading scanner.    MRP        = VWAP (daily res, Compute MRP, Daily POC, and Weekly POC from 1-minute OHLCV data.      Parameters, _calc_tp(), _make_df(), _ms(), _patched_levels(), Unit tests for btc_agent/scanner/levels.py and _calc_tp in trading/scanner.py. (+26 more)

### Community 8 - "Notifiers & Delivery"
Cohesion: 0.09
Nodes (31): deliver(), deliver_scan(), print_terminal(), Deliver scan results with channel-specific formatting., Send a payload to Telegram's sendMessage and log errors clearly., Send one or more HTML-formatted messages (Telegram caps each at 4096 chars)., send_desktop(), send_email() (+23 more)

### Community 9 - "OHLCV Aggregation"
Cohesion: 0.11
Nodes (19): aggregate_tf(), Aggregate 1m OHLCV into TF bars that match TradingView exactly.      TradingView, _make_1m_data(), Unit tests for btc_agent/scanner/aggregator.py  Key invariant: stub bars (partia, 43m: bars_per_day=33, max_minute=1419, waste=21min., 38m: bars_per_day=37, max_minute=1406, waste=34min., All returned bar open times must be in ascending order., No bar should span across a day boundary.         bar_open_time and bar_close_ti (+11 more)

### Community 10 - "Coinbase Executor & Tests"
Cohesion: 0.09
Nodes (10): _make_urlopen_mock(), Unit tests for btc_agent/trading/executor.py  All network calls are mocked — no, Long position take-profit: sell when price rises above target., Short position take-profit: buy when price falls below target., Return a context-manager mock that yields a fake HTTP response., TestPlaceMarketOrder, TestPlaceStopLimitOrder, TestPlaceTakeProfitOrder (+2 more)

### Community 11 - "Config Validation"
Cohesion: 0.13
Nodes (8): Unit tests for the _validate() function in btc_agent/config.py. Patches module-l, Run _validate() with specific config values temporarily overridden., TestInvalidPatterns, TestInvalidPort, TestInvalidTFRange, TestInvalidTimeFormat, TestValidConfig, _validate_with()

### Community 12 - "Strategy Docs & Lessons"
Cohesion: 0.09
Nodes (24): Web App SPA Template (index.html), Firebase Web SDK Config (Jinja2 Variables), Lesson: 4-Flag Trigger Uses Body High Not Wick, Lesson: calc_sl Always Uses Wick, Lesson: Firebase Auth Domain Must Match Exactly, Lesson: EC2 PEM Key Newline Mangling, Login Page Template (login.html), BTC AI Agent Project (+16 more)

### Community 13 - "Briefing Agent"
Cohesion: 0.12
Nodes (15): Main briefing entry point.     Fetches news, summarizes via Claude, delivers, an, run_briefing(), fetch_all(), fetch_reddit(), fetch_rss(), Fetch news from free RSS feeds and Reddit. No API keys required., _build_news_block(), summarize() (+7 more)

### Community 14 - "Coinbase API Client"
Cohesion: 0.14
Nodes (19): _auth_headers(), _b64url(), _build_jwt(), cancel_order(), _get(), get_portfolio_name(), _normalize_pem(), place_market_order() (+11 more)

### Community 15 - "Engulfing Patterns"
Cohesion: 0.25
Nodes (8): _detect_bearish_engulfing(), _detect_bullish_engulfing(), detect_engulfing(), Pattern detection functions. Each accepts bars: np.ndarray of shape (N, 5) — [op, Bullish engulfing: bars[-2] is bearish, bars[-1] is bullish and fully engulfs ba, _make_bars(), candles: list of (open, high, low, close, volume), TestEngulfing

### Community 16 - "Market Data Fetcher"
Cohesion: 0.29
Nodes (9): fetch_1m_candles(), fetch_current_price(), _fetch_ohlcv(), _get_exchange(), _get_exchange_cached(), Return (exchange, symbol) for the first venue that is reachable.     Skips excha, Lightweight single-call price fetch using a cached exchange connection., Fetch OHLCV with exponential backoff on rate limit errors. (+1 more)

### Community 17 - "Risk & Strategy Concepts"
Cohesion: 0.38
Nodes (7): Shared 150x Leverage Risk (500pt Liquidation Buffer), Mean-Reversion Scalping Logic, Strategy 2: Ping Pong Strategy, Ping Pong Session Zone, Strategy 3: Escalator Strategy, Escalator Trailing Stop Grid, Escalator as High-Volatility Complement to Ping Pong

### Community 18 - "4-Flag Pattern Logic"
Cohesion: 0.33
Nodes (4): detect_4flag_pattern(), fetch_binance_perp(), Detect GTI 4-Flag candlestick pattern.      Rules:       1. 4 consecutive altern, Fetch Binance perpetual futures OHLCV data.     interval: 1m, 3m, 5m, 15m, 30m,

### Community 20 - "App Config"
Cohesion: 0.5
Nodes (2): apply_settings(), Override module-level config vars from a Firestore settings dict.

### Community 21 - "Debug Tools"
Cohesion: 1.0
Nodes (1): Debug a specific timeframe — shows bars and exactly why patterns pass/fail. Usag

### Community 27 - "Market Order Op"
Cohesion: 1.0
Nodes (1): Place an immediate market order.          side: "BUY" or "SELL"         qty:  qu

### Community 28 - "Stop-Limit Order Op"
Cohesion: 1.0
Nodes (1): Place a GTC stop-limit order for stop-loss protection.

### Community 29 - "Cancel Order Op"
Cohesion: 1.0
Nodes (1): Cancel an open order by its broker-assigned order_id.

### Community 30 - "Contract Size"
Cohesion: 1.0
Nodes (1): BTC equivalent per unit/contract — used for PnL calculation.

## Knowledge Gaps
- **98 isolated node(s):** `Fetch Binance perpetual futures OHLCV data.     interval: 1m, 3m, 5m, 15m, 30m,`, `Detect GTI 4-Flag candlestick pattern.      Rules:       1. 4 consecutive altern`, `BTC AI Agent — CLI entrypoint  Usage:   python main.py brief     Run morning bri`, `Filter out noisy /api/status poll lines from uvicorn access logs.`, `Debug a specific timeframe — shows bars and exactly why patterns pass/fail. Usag` (+93 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `App Config`** (4 nodes): `apply_settings()`, `config.py`, `Override module-level config vars from a Firestore settings dict.`, `_validate()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Debug Tools`** (2 nodes): `Debug a specific timeframe — shows bars and exactly why patterns pass/fail. Usag`, `debug_tf.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Market Order Op`** (1 nodes): `Place an immediate market order.          side: "BUY" or "SELL"         qty:  qu`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Stop-Limit Order Op`** (1 nodes): `Place a GTC stop-limit order for stop-loss protection.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Cancel Order Op`** (1 nodes): `Cancel an open order by its broker-assigned order_id.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Contract Size`** (1 nodes): `BTC equivalent per unit/contract — used for PnL calculation.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_trading_scanner()` connect `Trading Scanner Core` to `Vishal Strategy Engine`, `Trading Models & Tests`, `Market Structure Levels`, `Notifiers & Delivery`, `Briefing Agent`, `Market Data Fetcher`?**
  _High betweenness centrality (0.259) - this node is a cross-community bridge._
- **Why does `get_broker()` connect `Broker Adapter Layer` to `Trading Scanner Core`?**
  _High betweenness centrality (0.155) - this node is a cross-community bridge._
- **Why does `_build_broker()` connect `Trading Scanner Core` to `Broker Adapter Layer`, `Trading Models & Tests`?**
  _High betweenness centrality (0.155) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `run_trading_scanner()` (e.g. with `main()` and `fetch_current_price()`) actually correct?**
  _`run_trading_scanner()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `Signal` (e.g. with `Vishal Sir Strategy detection functions. Called each tick from run_trading_scann` and `Create a signal that fires on the next price tick.`) actually correct?**
  _`Signal` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `get_state()` (e.g. with `trading_state()` and `trading_start()`) actually correct?**
  _`get_state()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Fetch Binance perpetual futures OHLCV data.     interval: 1m, 3m, 5m, 15m, 30m,`, `Detect GTI 4-Flag candlestick pattern.      Rules:       1. 4 consecutive altern`, `BTC AI Agent — CLI entrypoint  Usage:   python main.py brief     Run morning bri` to the rest of the system?**
  _98 weakly-connected nodes found - possible documentation gaps or missing edges._