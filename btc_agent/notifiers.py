import smtplib
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
from rich.console import Console
from rich.panel import Panel

from btc_agent import config

console = Console()


def print_terminal(title: str, message: str) -> None:
    console.print(Panel(message, title=title, border_style="cyan"))


def _telegram_post(payload: dict) -> None:
    """Send a payload to Telegram's sendMessage and log errors clearly."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        console.print("[yellow]Telegram not configured, skipping.[/yellow]")
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = httpx.post(url, json=payload, timeout=10)
        if not resp.is_success:
            console.print(f"[red]Telegram error {resp.status_code}: {resp.text}[/red]")
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        pass  # already printed above
    except Exception:
        console.print(f"[red]Telegram send failed:[/red]\n{traceback.format_exc()}")


def send_telegram(message: str) -> None:
    _telegram_post({"chat_id": config.TELEGRAM_CHAT_ID, "text": message})


def send_trade_alert(chat_id: str, message: str) -> None:
    """Send a trade event alert to a user's personal Telegram chat."""
    if not chat_id or not config.TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = httpx.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        if not resp.is_success:
            console.print(f"[yellow]Trade alert send failed {resp.status_code}: {resp.text}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Trade alert send error: {e}[/yellow]")


def _send_telegram_html(messages: list[str]) -> None:
    """Send one or more HTML-formatted messages (Telegram caps each at 4096 chars)."""
    for msg in messages:
        _telegram_post({
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
        })


def send_email(subject: str, body: str, to: str | None = None) -> None:
    if not config.EMAIL_USER or not config.EMAIL_PASS:
        console.print("[yellow]Email not configured, skipping.[/yellow]")
        return
    recipient = to or config.EMAIL_TO
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_USER
    msg["To"] = recipient
    msg.attach(MIMEText(body, "plain"))
    try:
        # Port 587 = STARTTLS, port 465 = SSL/TLS — try both
        if config.EMAIL_SMTP_PORT == 465:
            with smtplib.SMTP_SSL(config.EMAIL_SMTP_HOST, 465, timeout=15) as smtp:
                smtp.login(config.EMAIL_USER, config.EMAIL_PASS)
                smtp.sendmail(config.EMAIL_USER, recipient, msg.as_string())
        else:
            try:
                with smtplib.SMTP(config.EMAIL_SMTP_HOST, config.EMAIL_SMTP_PORT, timeout=15) as smtp:
                    smtp.starttls()
                    smtp.login(config.EMAIL_USER, config.EMAIL_PASS)
                    smtp.sendmail(config.EMAIL_USER, recipient, msg.as_string())
            except (TimeoutError, OSError):
                # Port 587 blocked — fall back to SSL on 465
                console.print("[yellow]Port 587 timed out, retrying on port 465 (SSL)…[/yellow]")
                with smtplib.SMTP_SSL(config.EMAIL_SMTP_HOST, 465, timeout=15) as smtp:
                    smtp.login(config.EMAIL_USER, config.EMAIL_PASS)
                    smtp.sendmail(config.EMAIL_USER, recipient, msg.as_string())
    except Exception:
        console.print(f"[red]Email send failed:[/red]\n{traceback.format_exc()}")


def send_desktop(title: str, message: str) -> None:
    try:
        import pync
        pync.notify(message[:250], title=title)
    except Exception:
        try:
            from plyer import notification
            notification.notify(title=title, message=message[:250], timeout=10)
        except Exception:
            console.print("[yellow]Desktop notification unavailable.[/yellow]")


def deliver(title: str, message: str, channels: list[str] | None = None) -> None:
    channels = channels or config.DELIVERY_CHANNELS
    if "terminal" in channels:
        print_terminal(title, message)
    if "telegram" in channels:
        send_telegram(f"{title}\n\n{message}")
    if "email" in channels:
        send_email(title, message)
    if "desktop" in channels:
        send_desktop(title, message)


def deliver_scan(hits: list, channels: list[str] | None = None) -> None:
    """Deliver scan results with channel-specific formatting."""
    # Import here to avoid circular imports
    from btc_agent.scanner.agent import _format_telegram, _format_email, _format_summary

    channels = channels or config.DELIVERY_CHANNELS
    title = "BTC Pattern Alert"

    if "terminal" in channels:
        print_terminal(title, _format_summary(hits))
    if "telegram" in channels:
        _send_telegram_html(_format_telegram(hits))
    if "email" in channels:
        send_email(title, _format_email(hits))
    if "desktop" in channels:
        send_desktop(title, f"{len(hits)} pattern signal(s) detected")
