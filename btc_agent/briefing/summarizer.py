import anthropic
from btc_agent import config

_PROMPT_TEMPLATE = """You are a professional crypto market analyst specializing in Bitcoin (BTC).

Below is a collection of today's news articles and Reddit posts from various sources.
Your job is to produce a concise morning briefing for a BTC perpetual trader.

NEWS & POSTS:
{news_block}

Please provide:
1. **Top 5 BTC-Relevant Stories** — summarize each in 1-2 sentences and explain how it may impact BTC price.
2. **Macro Sentiment** — overall bullish / bearish / neutral assessment with a brief reason.
3. **Key Risk Events** — any wars, political events, regulatory news, or major world-leader statements that could affect risk appetite.
4. **BTC Outlook** — short-term (24h) price bias and key levels to watch.

Keep the briefing concise and actionable. No fluff.
"""


def _build_news_block(data: dict) -> str:
    lines = []
    for item in data.get("rss", []):
        lines.append(
            f"[{item['source']}] {item['title']}\n{item['summary']}\n"
        )
    for post in data.get("reddit", []):
        lines.append(
            f"[{post['source']} | score:{post['score']}] {post['title']}\n"
        )
    return "\n".join(lines[:60])  # cap context size


def summarize(data: dict) -> str:
    if not config.ANTHROPIC_API_KEY:
        return (
            "⚠️ ANTHROPIC_API_KEY not set. "
            "Add it to .env to enable AI-generated briefings.\n\n"
            f"Raw headlines fetched: {len(data.get('rss', []))} RSS, "
            f"{len(data.get('reddit', []))} Reddit posts."
        )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    news_block = _build_news_block(data)
    prompt = _PROMPT_TEMPLATE.format(news_block=news_block)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
