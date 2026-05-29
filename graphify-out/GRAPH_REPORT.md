# Graph Report - btc-ai-agent  (2026-05-29)

## Corpus Check
- 51 files · ~53,262 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 935 nodes · 1869 edges · 58 communities detected
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 319 edges (avg confidence: 0.7)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]

## God Nodes (most connected - your core abstractions)
1. `run_trading_scanner()` - 48 edges
2. `Signal` - 41 edges
3. `get_state()` - 35 edges
4. `Position` - 34 edges
5. `_sc()` - 34 edges
6. `fetchJSON()` - 32 edges
7. `_execute_entry()` - 27 edges
8. `BrokerAdapter` - 25 edges
9. `TradeResult` - 23 edges
10. `bar()` - 23 edges

## Surprising Connections (you probably didn't know these)
- `Lesson: calc_sl Always Uses Wick` --conceptually_related_to--> `Chauke Zone Upper/Lower Line Entry Rules`  [INFERRED]
  tasks/lesson.md → strategies/4 Chauke pe Chauka Strategy PDF.pdf
- `main()` --calls--> `run_scanner()`  [INFERRED]
  main.py → btc_agent/scanner/agent.py
- `main()` --calls--> `run_trading_scanner()`  [INFERRED]
  main.py → btc_agent/trading/scanner.py
- `main()` --calls--> `start()`  [INFERRED]
  main.py → btc_agent/scheduler.py
- `Signal` --uses--> `TestEngulfing`  [INFERRED]
  btc_agent/trading/models.py → tests/test_trading.py

## Hyperedges (group relationships)
- **All 6 Trading Strategies Share GTI Zone Infrastructure** — strategy_1_gti_zones, strategy_4_zone_entry_rules, strategy_5_sunday_weekly_entry, strategy_6_t1_t2_split, shared_gti_zone_infrastructure [EXTRACTED 0.95]
- **Ping Pong and Escalator Co-exist on Same Chart for Sideways vs Trending Regimes** — strategy_2_ping_pong, strategy_3_escalator, strategy_3_volatility_complement, strategy_2_session_zone [EXTRACTED 0.92]
- **Firebase Credential Remediation Spanning config.py, app.py, and Both HTML Templates** — web_app_firebase_remediation, index_html_firebase_config, login_html, index_html [EXTRACTED 1.00]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (50): ABC, BrokerAdapter, BrokerAdapter, Return a human-readable account name from the broker API., Minimal interface every broker must implement., BybitAdapter, Bybit V5 Linear Perpetual Futures via REST API., CoinbaseAdapter (+42 more)

### Community 1 - "Community 1"
Cohesion: 0.03
Nodes (80): BaseHTTPMiddleware, get_firebase_app(), Shared Firebase Admin App — initialised once, reused by auth and Firestore modul, get_regime(), Return cached regime. Thread-safe, no I/O., get_all_regimes(), Return copy of in-memory cache. Thread-safe, no I/O., _bg() (+72 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (85): _activateSubTab(), addMarkovCustomTicker(), _adminSetMode(), _adminStopUser(), _applyHistFilters(), _applyPrice(), cancelPosition(), connectPepperstone() (+77 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (35): Tests for the trading scanner:   - detect_engulfing pattern   - calc_sl (wick of, Tests for _trail_sl() ratchet logic., Regression: overlapping rolling windows used to emit a cluster of     near-ident, TestCalcSL, TestFourFlagLatestWindow, TestQtyValidation, TestSameTfDirectionGuard, TestSignalExpiry (+27 more)

### Community 4 - "Community 4"
Cohesion: 0.1
Nodes (63): _active_patterns(), _all_swing_highs(), _all_swing_lows(), _append_history(), _bars_to_signal(), _bias_filter_enabled(), _bsg_enabled(), _bsg_trade_enabled() (+55 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (20): _ist(), Unit tests for Vishal Sir strategy detection functions., _sc(), TestChaukepeChauka, TestDoubleProfit, TestEscalator, TestHighWinRate, TestPingPong (+12 more)

### Community 6 - "Community 6"
Cohesion: 0.09
Nodes (40): compute_levels(), Market structure levels for the trading scanner.    MRP        = VWAP (daily res, Compute MRP, Daily POC, and Weekly POC from 1-minute OHLCV data.      Parameters, _calc_tp(), _FakeScanner, _make_df(), _ms(), _patched_levels() (+32 more)

### Community 7 - "Community 7"
Cohesion: 0.12
Nodes (15): detect_4flag(), detect_evening_star(), detect_morning_star(), Bearish 3-candle reversal:       Bar 0: large bullish candle       Bar 1: small, 4 Flags Whale Pattern — matches the Pine Script logic exactly:      1. Alternati, Bullish 3-candle reversal:       Bar 0: large bearish candle       Bar 1: small, bar(), bars() (+7 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (35): deliver(), deliver_scan(), print_terminal(), Deliver scan results with channel-specific formatting., Send a payload to Telegram's sendMessage and log errors clearly., Send one or more HTML-formatted messages (Telegram caps each at 4096 chars)., Send one or more HTML-formatted messages (Telegram caps each at 4096 chars)., send_desktop() (+27 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (29): Main briefing entry point.     Fetches news, summarizes via Claude, delivers, an, run_briefing(), fetch_all(), fetch_reddit(), fetch_rss(), Fetch news from free RSS feeds and Reddit. No API keys required., _build_news_block(), summarize() (+21 more)

### Community 10 - "Community 10"
Cohesion: 0.11
Nodes (19): aggregate_tf(), Aggregate 1m OHLCV into TF bars that match TradingView exactly.      TradingView, _make_1m_data(), Unit tests for btc_agent/scanner/aggregator.py  Key invariant: stub bars (partia, 43m: bars_per_day=33, max_minute=1419, waste=21min., 38m: bars_per_day=37, max_minute=1406, waste=34min., All returned bar open times must be in ascending order., No bar should span across a day boundary.         bar_open_time and bar_close_ti (+11 more)

### Community 11 - "Community 11"
Cohesion: 0.1
Nodes (11): _decode_jwt_segment(), _make_urlopen_mock(), Unit tests for btc_agent/trading/executor.py  All network calls are mocked — no, Long position take-profit: sell when price rises above target., Short position take-profit: buy when price falls below target., Return a context-manager mock that yields a fake HTTP response., TestAuthHeaders, TestPlaceMarketOrder (+3 more)

### Community 12 - "Community 12"
Cohesion: 0.16
Nodes (25): append_csv(), capture_y_axis_map(), classify_pixel(), collect_all_lines(), collect_main(), _configure_logging(), debug_main(), detect_lines() (+17 more)

### Community 13 - "Community 13"
Cohesion: 0.13
Nodes (8): Unit tests for the _validate() function in btc_agent/config.py. Patches module-l, Run _validate() with specific config values temporarily overridden., TestInvalidPatterns, TestInvalidPort, TestInvalidTFRange, TestInvalidTimeFormat, TestValidConfig, _validate_with()

### Community 14 - "Community 14"
Cohesion: 0.14
Nodes (19): _auth_headers(), _b64url(), _build_jwt(), cancel_order(), _get(), get_portfolio_name(), _normalize_pem(), place_market_order() (+11 more)

### Community 15 - "Community 15"
Cohesion: 0.12
Nodes (17): Lesson: 4-Flag Trigger Uses Body High Not Wick, Lesson: calc_sl Always Uses Wick, Lesson: Firebase Auth Domain Must Match Exactly, Lesson: EC2 PEM Key Newline Mangling, GTI Zone Infrastructure (Shared Across Strategies), Entry Candle Rules (Full-Body Breakout/Breakdown), GTI (Go To Indikator) Zones, Strategy 1: High Win Rate Trading (+9 more)

### Community 16 - "Community 16"
Cohesion: 0.19
Nodes (14): _compute_regime(), _fetch_close(), _label(), Daily Markov regime computation for BTC-USD.  App-level singleton (not per-user), Compute yesterday's actual regime label and update Firestore., Background thread target — compute and cache regime., Synchronous refresh — called once at scanner startup., Non-blocking daily refresh — called inside the scan-interval block. (+6 more)

### Community 17 - "Community 17"
Cohesion: 0.25
Nodes (8): _detect_bearish_engulfing(), _detect_bullish_engulfing(), detect_engulfing(), Pattern detection functions. Each accepts bars: np.ndarray of shape (N, 5) — [op, Bullish engulfing: bars[-2] is bearish, bars[-1] is bullish and fully engulfs ba, _make_bars(), candles: list of (open, high, low, close, volume), TestEngulfing

### Community 18 - "Community 18"
Cohesion: 0.26
Nodes (2): BinanceAdapter, Binance USDT-M Perpetual Futures via REST API.

### Community 19 - "Community 19"
Cohesion: 0.29
Nodes (10): _aggregate(), compute_oi_signals(), _fetch_btc_price(), fetch_oi_snapshot(), _fetch_raw_oi(), OISignals, OISnapshot, Fetch current BTC/USDT price from Binance spot — needed to convert USDT-M OI (BT (+2 more)

### Community 20 - "Community 20"
Cohesion: 0.25
Nodes (10): fetch_1m_candles(), fetch_current_price(), _fetch_ohlcv(), _get_exchange(), _get_exchange_cached(), Return (exchange, symbol) for the first venue that is reachable.     Skips excha, Lightweight single-call price fetch using a cached exchange connection., Fetch OHLCV with exponential backoff on rate limit errors. (+2 more)

### Community 21 - "Community 21"
Cohesion: 0.38
Nodes (7): Shared 150x Leverage Risk (500pt Liquidation Buffer), Mean-Reversion Scalping Logic, Strategy 2: Ping Pong Strategy, Ping Pong Session Zone, Strategy 3: Escalator Strategy, Escalator Trailing Stop Grid, Escalator as High-Volatility Complement to Ping Pong

### Community 22 - "Community 22"
Cohesion: 0.33
Nodes (4): detect_4flag_pattern(), fetch_binance_perp(), Detect GTI 4-Flag candlestick pattern.      Rules:       1. 4 consecutive altern, Fetch Binance perpetual futures OHLCV data.     interval: 1m, 3m, 5m, 15m, 30m,

### Community 24 - "Community 24"
Cohesion: 0.5
Nodes (2): apply_settings(), Override module-level config vars from a Firestore settings dict.

### Community 25 - "Community 25"
Cohesion: 0.67
Nodes (3): BTC AI Agent Project, Task Backlog & Todo, Security Backlog

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (1): Debug a specific timeframe — shows bars and exactly why patterns pass/fail. Usag

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (1): Place an immediate market order.          side: "BUY" or "SELL"         qty:  qu

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): Place a GTC stop-limit order for stop-loss protection.

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): Place a GTC take-profit order that closes the position when TP is reached.

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Cancel an open order by its broker-assigned order_id.

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): BTC equivalent per unit/contract — used for PnL calculation.

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): Override module-level config vars from a Firestore settings dict.

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): Deliver scan results with channel-specific formatting.

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): qty must be a positive integer that is a multiple of 2.

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): Called by frontend on login — restarts scanner if Firestore says it was running.

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Run fn(*args) in a daemon thread — fire and forget.

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Read all three collections for the given uid, or None if Firestore is unavailabl

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Return the name of the user's default Coinbase portfolio.

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Place an immediate market order (IOC).

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Place a GTC stop-limit order for stop-loss.

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Cancel a single order. Uses batch_cancel endpoint.

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Place a GTC take-profit limit order.

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Cancel an open order by its broker-assigned order_id.

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): BTC equivalent per unit/contract — used for PnL calculation.

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Return a human-readable account name from the broker API.

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Call compute_levels with a fixed 'now' so tests are deterministic.

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Yesterday's candles must not affect MRP.

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): VWAP = Σ(tp × vol) / Σ(vol) across today's candles.

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): Daily POC = (prev_H + prev_L + prev_C) / 3 from yesterday's candles.

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Weekly POC = weekly_open × (1 + weekly_adj / 100).

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): weekly_open = open of the very first 1m candle of the current week.

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): Import and call _calc_tp with a temporary min_tp of 500.

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): If nearest level is only 100 pts above entry, TP should be floored at entry + 50

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): No levels above entry → fixed_500 fallback.

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (1): None values for individual levels must be skipped (not raise TypeError).

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Return a context-manager mock that yields a fake HTTP response.

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): Long position take-profit: sell when price rises above target.

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): Short position take-profit: buy when price falls below target.

## Knowledge Gaps
- **154 isolated node(s):** `Fetch Binance perpetual futures OHLCV data.     interval: 1m, 3m, 5m, 15m, 30m,`, `Detect GTI 4-Flag candlestick pattern.      Rules:       1. 4 consecutive altern`, `BTC AI Agent — CLI entrypoint  Usage:   python main.py brief     Run morning bri`, `Filter out noisy /api/status poll lines from uvicorn access logs.`, `Debug a specific timeframe — shows bars and exactly why patterns pass/fail. Usag` (+149 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 18`** (13 nodes): `BinanceAdapter`, `.cancel_order()`, `._delete()`, `._headers()`, `.__init__()`, `.place_market_order()`, `.place_stop_limit_order()`, `.place_take_profit_order()`, `._post()`, `._sign()`, `contract_size()`, `Binance USDT-M Perpetual Futures via REST API.`, `binance.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (4 nodes): `apply_settings()`, `config.py`, `Override module-level config vars from a Firestore settings dict.`, `_validate()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (2 nodes): `Debug a specific timeframe — shows bars and exactly why patterns pass/fail. Usag`, `debug_tf.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `Place an immediate market order.          side: "BUY" or "SELL"         qty:  qu`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `Place a GTC stop-limit order for stop-loss protection.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `Place a GTC take-profit order that closes the position when TP is reached.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Cancel an open order by its broker-assigned order_id.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `BTC equivalent per unit/contract — used for PnL calculation.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `Override module-level config vars from a Firestore settings dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `Deliver scan results with channel-specific formatting.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `qty must be a positive integer that is a multiple of 2.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `Called by frontend on login — restarts scanner if Firestore says it was running.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `Run fn(*args) in a daemon thread — fire and forget.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `Read all three collections for the given uid, or None if Firestore is unavailabl`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `Return the name of the user's default Coinbase portfolio.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Place an immediate market order (IOC).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Place a GTC stop-limit order for stop-loss.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `Cancel a single order. Uses batch_cancel endpoint.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `Place a GTC take-profit limit order.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `Cancel an open order by its broker-assigned order_id.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `BTC equivalent per unit/contract — used for PnL calculation.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `Return a human-readable account name from the broker API.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Call compute_levels with a fixed 'now' so tests are deterministic.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Yesterday's candles must not affect MRP.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `VWAP = Σ(tp × vol) / Σ(vol) across today's candles.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `Daily POC = (prev_H + prev_L + prev_C) / 3 from yesterday's candles.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `Weekly POC = weekly_open × (1 + weekly_adj / 100).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `weekly_open = open of the very first 1m candle of the current week.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `Import and call _calc_tp with a temporary min_tp of 500.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `If nearest level is only 100 pts above entry, TP should be floored at entry + 50`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `No levels above entry → fixed_500 fallback.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `None values for individual levels must be skipped (not raise TypeError).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `Return a context-manager mock that yields a fake HTTP response.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `Long position take-profit: sell when price rises above target.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `Short position take-profit: buy when price falls below target.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_trading_scanner()` connect `Community 4` to `Community 3`, `Community 5`, `Community 6`, `Community 8`, `Community 9`, `Community 10`, `Community 16`, `Community 19`, `Community 20`?**
  _High betweenness centrality (0.257) - this node is a cross-community bridge._
- **Why does `get_broker()` connect `Community 0` to `Community 18`, `Community 4`?**
  _High betweenness centrality (0.173) - this node is a cross-community bridge._
- **Why does `_build_broker()` connect `Community 4` to `Community 0`, `Community 3`?**
  _High betweenness centrality (0.172) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `run_trading_scanner()` (e.g. with `main()` and `refresh_regime_blocking()`) actually correct?**
  _`run_trading_scanner()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 40 inferred relationships involving `Signal` (e.g. with `Vishal Sir Strategy detection functions. Called each tick from run_trading_scann` and `Create a signal that fires on the next price tick.`) actually correct?**
  _`Signal` has 40 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `get_state()` (e.g. with `trading_state()` and `trading_start()`) actually correct?**
  _`get_state()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 33 inferred relationships involving `Position` (e.g. with `_Scanner` and `Trading Scanner — scans 15m–90m TFs for 4-Flag and Engulfing patterns, monitors`) actually correct?**
  _`Position` has 33 INFERRED edges - model-reasoned connections that need verification._