import signal
import time

import schedule
from rich.console import Console

from btc_agent import config
from btc_agent.briefing.agent import run_briefing
from btc_agent.scanner.agent import run_scanner

console = Console()

_shutdown = False


def _handle_signal(sig, frame) -> None:
    global _shutdown
    _shutdown = True
    console.print("\n[yellow]Shutdown signal received, stopping after current task…[/yellow]")


signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def start() -> None:
    console.rule("[bold cyan]BTC Agent Scheduler[/bold cyan]")

    schedule.every().day.at(config.BRIEFING_TIME, "UTC").do(_safe_brief)

    if config.SCANNER_INTERVAL_MIN:
        console.print(
            f"Daily briefing at [bold]{config.BRIEFING_TIME}[/bold] UTC, "
            f"scanner every [bold]{config.SCANNER_INTERVAL_MIN}m[/bold]"
        )
        schedule.every(config.SCANNER_INTERVAL_MIN).minutes.do(_safe_scan)
    else:
        console.print(
            f"Daily briefing at [bold]{config.BRIEFING_TIME}[/bold] UTC, "
            f"scanner at [bold]{config.SCANNER_TIME}[/bold] UTC"
        )
        schedule.every().day.at(config.SCANNER_TIME, "UTC").do(_safe_scan)

    schedule.every().day.at("01:20", "UTC").do(_safe_markov)
    console.print("[green]Scheduler running. Press Ctrl+C to stop.[/green]")
    while not _shutdown:
        schedule.run_pending()
        time.sleep(30)
    console.print("[green]Scheduler stopped cleanly.[/green]")


_RETRY_DELAYS = [60, 300, 900]  # seconds: 1m, 5m, 15m between retries


def _safe_markov() -> None:
    try:
        from btc_agent.scanner.markov_tickers import refresh_all_tickers
        refresh_all_tickers()
    except Exception as e:
        console.print(f"[yellow]Markov refresh failed: {e}[/yellow]")


def _safe_brief() -> None:
    try:
        run_briefing()
    except Exception as e:
        console.print(f"[red]Briefing error: {e}[/red]")


def _safe_scan() -> None:
    for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
        if delay > 0:
            console.print(f"[yellow]Scanner retry {attempt}/{len(_RETRY_DELAYS) + 1} in {delay}s…[/yellow]")
            time.sleep(delay)
        try:
            run_scanner()
            return
        except Exception as e:
            console.print(f"[red]Scanner error (attempt {attempt}): {e}[/red]")
    console.print("[red]Scanner failed after all retries — will try again at next scheduled interval.[/red]")
