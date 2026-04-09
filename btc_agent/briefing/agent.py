from rich.console import Console

from btc_agent import notifiers, storage
from btc_agent.briefing.fetcher import fetch_all
from btc_agent.briefing.summarizer import summarize

console = Console()


def run_briefing() -> str:
    """
    Main briefing entry point.
    Fetches news, summarizes via Claude, delivers, and persists.
    Returns the briefing text.
    """
    console.rule("[bold cyan]BTC Morning Briefing[/bold cyan]")
    console.print("Fetching news sources...")

    data = fetch_all()
    console.print("Generating AI summary...")

    text = summarize(data)

    storage.save_briefing(text)
    notifiers.deliver("BTC Morning Briefing", text)

    return text
