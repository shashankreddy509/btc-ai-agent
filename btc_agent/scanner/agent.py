from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))

from rich.console import Console
from rich.table import Table

from btc_agent import config, notifiers, storage
from btc_agent.scanner.aggregator import aggregate_tf, df_to_numpy
from btc_agent.scanner.data import fetch_1m_candles
from btc_agent.scanner.depo import check_depo, generate_depo_lines
from btc_agent.scanner.patterns import PATTERNS

console = Console()

_LOOKBACK_BARS = 10


def run_scanner() -> list[dict]:
    console.rule("[bold cyan]BTC Pattern Scanner[/bold cyan]")

    df = fetch_1m_candles()
    arr, ts_arr, minutes_of_day, unix_days = df_to_numpy(df)
    depo_lines = generate_depo_lines()

    tf_min = config.SCANNER_TF_MIN
    tf_max = config.SCANNER_TF_MAX
    total_tfs = tf_max - tf_min + 1

    active_patterns = {
        name: fn
        for name, fn in PATTERNS.items()
        if name in config.SCANNER_PATTERNS
    }
    if not active_patterns:
        console.print("[red]No valid patterns in SCANNER_PATTERNS. Check your .env.[/red]")
        return []

    console.print(
        f"Scanning [bold]{total_tfs}[/bold] timeframes ({tf_min}m → {tf_max}m), "
        f"lookback=[bold]{_LOOKBACK_BARS}[/bold] bars, "
        f"patterns=[bold]{', '.join(active_patterns)}[/bold], "
        f"[bold]{len(depo_lines)}[/bold] DEPO levels…"
    )

    hits: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for tf in range(tf_min, tf_max + 1):
        bars, bar_open_times = aggregate_tf(
            arr, ts_arr, minutes_of_day, unix_days, tf, last_n=_LOOKBACK_BARS
        )
        if bars is None:
            continue

        bars_per_day = 1440 // tf

        for pattern_name, detector in active_patterns.items():
            # 4-Flag requires tight consolidation candles.
            # When bars_per_day == 1 (TF > 720m), each bar is a ~13+ hour
            # candle — adjacent TFs all produce the same daily bars and the
            # pattern has no meaningful structure.  Skip to avoid noise.
            if pattern_name == "4-Flag" and bars_per_day == 1:
                continue

            window = 4 if pattern_name == "4-Flag" else 3
            if len(bars) < window:
                continue

            max_offset = len(bars) - window
            for offset in range(max_offset + 1):
                if offset == 0:
                    window_bars = bars[-window:]
                else:
                    window_bars = bars[-(window + offset): -offset]

                if detector(window_bars):
                    depo_hit = check_depo(window_bars, depo_lines)

                    # Open price of the last bar in the pattern
                    bar_open_price = float(window_bars[-1, 0])

                    bar_open_ts = int(bar_open_times[-(offset + 1)])
                    bar_open_time = datetime.fromtimestamp(
                        bar_open_ts, tz=timezone.utc
                    ).isoformat()

                    hits.append(
                        {
                            "tf": f"{tf}m",
                            "pattern": pattern_name,
                            "bars_ago": offset,
                            "bar_open_time": bar_open_time,
                            "bar_open_price": bar_open_price,
                            "depo_line": depo_hit,
                            "timestamp": now,
                        }
                    )

    _display(hits)
    storage.save_scan(hits)
    if hits:
        notifiers.deliver_scan(hits)
    else:
        console.print("[yellow]No patterns found in this scan.[/yellow]")

    return hits


def _to_ist(iso_str: str) -> str:
    """Convert an ISO-format UTC timestamp string to IST (dd-MMM-YYYY HH:MM IST)."""
    dt_utc = datetime.fromisoformat(iso_str).replace(tzinfo=timezone.utc)
    dt_ist = dt_utc.astimezone(_IST)
    return dt_ist.strftime("%d-%b-%Y %H:%M")


def _display(hits: list[dict]) -> None:
    table = Table(title="Pattern Scan Results", border_style="cyan")
    table.add_column("TF", style="bold green")
    table.add_column("Pattern", style="bold yellow")
    table.add_column("Bars Ago", justify="right")
    table.add_column("Bar Open (IST)", style="cyan")
    table.add_column("Open Price", justify="right", style="bold white")
    table.add_column("DEPO Line", style="bold magenta")

    if not hits:
        table.add_row("-", "No patterns found", "-", "-", "-", "-")
    else:
        for h in hits:
            depo_str  = f"{h['depo_line']:,.0f}" if h["depo_line"] else "none"
            bars_ago  = str(h["bars_ago"]) if h["bars_ago"] > 0 else "[dim]current[/dim]"
            open_time = _to_ist(h["bar_open_time"])
            open_px   = f"{h['bar_open_price']:,.1f}"
            table.add_row(h["tf"], h["pattern"], bars_ago, open_time, open_px, depo_str)

    console.print(table)


def _group_hits(hits: list[dict]) -> list[dict]:
    """
    Collapse hits that share the same (pattern, bar_open_time, depo_line) into one
    entry with a TF range label.  Avoids e.g. 801m / 802m / 803m … all reporting
    the same daily bar.
    """
    from collections import defaultdict
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for h in hits:
        key = (h["pattern"], h["bar_open_time"][:16], h["depo_line"])
        buckets[key].append(h)

    grouped = []
    for (pattern, open_time, depo), group in buckets.items():
        tfs = sorted(int(h["tf"].rstrip("m")) for h in group)
        if len(tfs) == 1:
            tf_label = f"{tfs[0]}m"
        else:
            # Build compact label: consecutive runs → "801-811m", gaps → "78m,94m"
            runs, run = [], [tfs[0]]
            for t in tfs[1:]:
                if t == run[-1] + 1:
                    run.append(t)
                else:
                    runs.append(run); run = [t]
            runs.append(run)
            parts = [f"{r[0]}m" if len(r) == 1 else f"{r[0]}-{r[-1]}m" for r in runs]
            tf_label = ", ".join(parts)

        rep = group[0]
        grouped.append({**rep, "tf": tf_label})

    # Sort: most recent bar first, then by raw tf value
    grouped.sort(key=lambda h: (h["bar_open_time"], h["bars_ago"]), reverse=True)
    return grouped


def _hit_lines_telegram(h: dict) -> str:
    """Single hit formatted as HTML for Telegram."""
    import html as _html
    depo_str  = f"{h['depo_line']:,.0f}" if h["depo_line"] else "—"
    ago       = "current bar" if h["bars_ago"] == 0 else f"{h['bars_ago']} bars ago"
    open_time = _to_ist(h["bar_open_time"])
    open_px   = f"{h['bar_open_price']:,.1f}"
    return (
        f"<b>{_html.escape(h['tf'])}</b> · {_html.escape(h['pattern'])} · {ago}\n"
        f"🕐 {open_time}\n"
        f"💵 Open: {open_px}  |  DEPO: {depo_str}"
    )


def _format_telegram(hits: list[dict]) -> list[str]:
    """Return a list of HTML messages (each ≤ 4096 chars) covering ALL hits."""
    header  = f"<b>🔔 BTC Pattern Alert</b>  —  {len(hits)} signal{'s' if len(hits)!=1 else ''}"
    blocks  = [_hit_lines_telegram(h) for h in hits]
    messages: list[str] = []
    current = header
    for block in blocks:
        candidate = current + "\n\n" + block
        if len(candidate) > 4096:
            messages.append(current)
            current = block          # start fresh message with this block
        else:
            current = candidate
    messages.append(current)
    return messages


def _format_email(hits: list[dict]) -> str:
    """Plain-text email body with all hits."""
    lines = [f"BTC Pattern Alert — {len(hits)} signal{'s' if len(hits)!=1 else ''}\n",
             f"{'─'*60}"]
    for h in hits:
        depo_str  = f"{h['depo_line']:,.0f}" if h["depo_line"] else "none"
        ago       = "current bar" if h["bars_ago"] == 0 else f"{h['bars_ago']} bars ago"
        open_time = _to_ist(h["bar_open_time"])
        open_px   = f"{h['bar_open_price']:,.1f}"
        lines.append(
            f"TF     : {h['tf']}\n"
            f"Pattern: {h['pattern']}  ({ago})\n"
            f"Opened : {open_time}  @  {open_px}\n"
            f"DEPO   : {depo_str}\n"
        )
    return "\n".join(lines)


def _format_summary(hits: list[dict]) -> str:
    """Compact plain-text for terminal / generic delivery."""
    lines = [f"BTC Pattern Scanner Results  ({len(hits)} signals)\n"]
    for h in hits:
        depo_str  = f"{h['depo_line']:,.0f}" if h["depo_line"] else "none"
        ago       = "current bar" if h["bars_ago"] == 0 else f"{h['bars_ago']} bars ago"
        open_time = _to_ist(h["bar_open_time"])
        open_px   = f"{h['bar_open_price']:,.1f}"
        lines.append(
            f"• {h['tf']} | {h['pattern']} | {ago} | "
            f"Open: {open_time} @ {open_px} | DEPO: {depo_str}"
        )
    return "\n".join(lines)
