"""
BTC AI Agent — CLI entrypoint

Usage:
  python main.py brief     Run morning briefing now
  python main.py scan      Run pattern scanner now
  python main.py oi        Show last 4 × 1H aggregated Open Interest candles
  python main.py run       Start scheduler daemon (briefing + scanner on schedule)
  python main.py web       Start web dashboard at http://localhost:8000
  python main.py all       Start scheduler + web dashboard together (for EC2)
"""
import argparse
import logging
import sys


def _suppress_status_log() -> None:
    """Filter out noisy /api/status poll lines from uvicorn access logs."""
    class _Filter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return "/api/status" not in record.getMessage()

    logging.getLogger("uvicorn.access").addFilter(_Filter())


def main():
    parser = argparse.ArgumentParser(
        description="BTC AI Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "command",
        choices=["brief", "scan", "oi", "trade", "run", "web", "all"],
        help="Command to execute",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Web server host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", default=8000, type=int, help="Web server port (default: 8000)"
    )
    args = parser.parse_args()

    if args.command == "brief":
        from btc_agent.briefing.agent import run_briefing
        run_briefing()

    elif args.command == "scan":
        from btc_agent.scanner.agent import run_scanner
        run_scanner()

    elif args.command == "oi":
        from btc_agent.scanner.oi import run_oi_display
        run_oi_display()

    elif args.command == "trade":
        from btc_agent.trading.scanner import run_trading_scanner
        run_trading_scanner()

    elif args.command == "run":
        from btc_agent.scheduler import start
        start()

    elif args.command == "web":
        import logging
        import uvicorn
        _suppress_status_log()
        print(f"Starting dashboard at http://{args.host}:{args.port}")
        uvicorn.run(
            "btc_agent.web.app:app",
            host=args.host,
            port=args.port,
            reload=False,
        )

    elif args.command == "all":
        # Run scheduler in a background thread, web server in the main thread
        import threading
        import uvicorn
        _suppress_status_log()
        from btc_agent.scheduler import start

        t = threading.Thread(target=start, daemon=True, name="scheduler")
        t.start()
        print(f"Starting dashboard at http://{args.host}:{args.port}")
        uvicorn.run(
            "btc_agent.web.app:app",
            host=args.host,
            port=args.port,
            reload=False,
        )


if __name__ == "__main__":
    main()
