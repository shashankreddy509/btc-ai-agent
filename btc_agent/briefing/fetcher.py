"""
Fetch news from free RSS feeds and Reddit.
No API keys required.
"""
import time
from datetime import datetime, timezone

import feedparser
import praw
from rich.console import Console

console = Console()

RSS_FEEDS = {
    "Reuters (Business)": "https://feeds.reuters.com/reuters/businessNews",
    "BBC Technology":     "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "CoinDesk":           "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "CryptoPanic":        "https://cryptopanic.com/news/rss/",
    "Cointelegraph":      "https://cointelegraph.com/rss",
    "Reuters (World)":    "https://feeds.reuters.com/reuters/worldNews",
}

REDDIT_SUBS = ["Bitcoin", "CryptoCurrency", "geopolitics"]
REDDIT_LIMIT = 15


def fetch_rss() -> list[dict]:
    articles = []
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                articles.append(
                    {
                        "source": source,
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", entry.get("description", ""))[:500],
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                    }
                )
        except Exception as e:
            console.print(f"[yellow]RSS fetch failed for {source}: {e}[/yellow]")
    console.print(f"[green]Fetched {len(articles)} RSS articles.[/green]")
    return articles


def fetch_reddit() -> list[dict]:
    posts = []
    try:
        # Read-only mode — no credentials needed for public subreddits
        reddit = praw.Reddit(
            client_id="public",
            client_secret="public",
            user_agent="btc-ai-agent/1.0 (research)",
        )
        for sub in REDDIT_SUBS:
            try:
                for post in reddit.subreddit(sub).hot(limit=REDDIT_LIMIT):
                    posts.append(
                        {
                            "source": f"r/{sub}",
                            "title": post.title,
                            "score": post.score,
                            "url": post.url,
                            "created_utc": datetime.fromtimestamp(
                                post.created_utc, tz=timezone.utc
                            ).isoformat(),
                        }
                    )
            except Exception as e:
                console.print(f"[yellow]Reddit fetch failed for r/{sub}: {e}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Reddit unavailable: {e}[/yellow]")
    console.print(f"[green]Fetched {len(posts)} Reddit posts.[/green]")
    return posts


def fetch_all() -> dict:
    return {
        "rss": fetch_rss(),
        "reddit": fetch_reddit(),
    }
