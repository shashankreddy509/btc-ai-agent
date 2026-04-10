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

    console.print("[green]Scheduler running. Press Ctrl+C to stop.[/green]")
    while not _shutdown:
        schedule.run_pending()
        time.sleep(30)
    console.print("[green]Scheduler stopped cleanly.[/green]")


def _safe_brief() -> None:
    try:
        run_briefing()
    except Exception as e:
        console.print(f"[red]Briefing error: {e}[/red]")


def _safe_scan() -> None:
    try:
        run_scanner()
    except Exception as e:
        console.print(f"[red]Scanner error: {e}[/red]")
