from rich.console import Console

from btc_agent import notifiers, storage
from btc_agent.briefing.fetcher import fetch_all
from btc_agent.briefing.summarizer import summarize

console = Console()


def run_briefing() -> str:
    """
    Main briefing entry point.
    Fetches news, summarizes via Claude, delivers, and persists.
    Falls back to the last cached briefing if all feeds are unreachable.
    Returns the briefing text.
    """
    console.rule("[bold cyan]BTC Morning Briefing[/bold cyan]")
    console.print("Fetching news sources...")

    try:
        data = fetch_all()
    except Exception as e:
        console.print(f"[red]Fetch error: {e} — falling back to cached briefing.[/red]")
        data = {}

    if not data.get("rss") and not data.get("reddit"):
        cached = storage.load_briefing()
        console.print("[yellow]No fresh data — delivering cached briefing.[/yellow]")
        notifiers.deliver("BTC Morning Briefing (cached)", cached["text"])
        return cached["text"]

    console.print("Generating AI summary...")
    try:
        text = summarize(data)
    except Exception as e:
        console.print(f"[red]Summarize failed: {e} — falling back to cached briefing.[/red]")
        cached = storage.load_briefing()
        return cached.get("text", "")
    storage.save_briefing(text)
    notifiers.deliver("BTC Morning Briefing", text)
    return text
