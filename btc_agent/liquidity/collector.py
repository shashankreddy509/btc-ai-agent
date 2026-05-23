"""
CoinGlass Liquidation Heatmap — Dynamic Leverage Collector (Playwright)

Kill-and-restart pattern: browser opens, scrapes, closes every 15 min.
Memory: ~400 MB for ~30s per cycle, then 0 during sleep.

Usage:
    uv run liquidity-debug     # one-shot hover + DOM dump, headed browser
    uv run liquidity-collect   # full 15-min loop, headless
"""

import asyncio
import csv
import io
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image
from playwright.async_api import async_playwright, Page

load_dotenv()

log = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
CHART_URL        = "https://legend.coinglass.com/chart/93ab9a7dbf63446c9c2b9944f10e6ef2"
SESSION_FILE     = Path(".coinglass_session.json")
INTERVAL_SECONDS = 15 * 60
OUTPUT_CSV       = "leverage_data.csv"
SCREENSHOT_DIR   = Path("screenshots")
VIEWPORT_WIDTH   = 1527
VIEWPORT_HEIGHT  = 805
HOVER_SETTLE_MS  = 800
CHART_LOAD_MS    = 8000

HOVER_X       = 1250
CHART_Y_START = 55
CHART_Y_END   = 740
LINE_MERGE_PX = 3

Y_AXIS_X      = (1325 + VIEWPORT_WIDTH) // 2
YAXIS_DRAG_PX = 200

CHART_X_END   = 1325

CG_EMAIL    = os.getenv("COINGLASS_EMAIL", "")
CG_PASSWORD = os.getenv("COINGLASS_PASSWORD", "")

# ── Color profiles ─────────────────────────────────────────────────────────────
COLOR_PROFILES = [
    ("YELLOW",  (220, 255), (220, 255), (0,   40)),
    ("LIME",    (160, 230), (220, 255), (0,   80)),
    ("ORANGE",  (220, 255), (80,  180), (0,   40)),
    ("RED",     (180, 255), (0,   60),  (0,   40)),
    ("TEAL",    (0,   80),  (150, 210), (150, 210)),
    ("NAVY",    (20,  80),  (20,  80),  (80,  160)),
    ("BLUE",    (0,   80),  (80,  180), (180, 255)),
    ("PURPLE",  (80,  180), (0,   80),  (120, 255)),
    ("PINK",    (180, 255), (0,   80),  (100, 220)),
    ("WHITE",   (200, 255), (200, 255), (200, 255)),
    ("CYAN",    (0,   80),  (200, 255), (200, 255)),
    ("GREEN",   (0,   80),  (160, 255), (0,   80)),
    ("BLACK",   (0,   25),  (0,   25),  (0,   25)),
]


def classify_pixel(r: int, g: int, b: int) -> str | None:
    for label, (rlo, rhi), (glo, ghi), (blo, bhi) in COLOR_PROFILES:
        if rlo <= r <= rhi and glo <= g <= ghi and blo <= b <= bhi:
            return label
    return None


# ── Canvas intercept (injected before every page load) ────────────────────────
CANVAS_INTERCEPT_JS = """
(function() {
    if (!location.hostname.includes('coinglass.com')) return;
    const proto = CanvasRenderingContext2D.prototype;
    const origFillText = proto.fillText;
    window._yAxisTicks = [];
    proto.fillText = function(text, x, y, ...args) {
        const clean = String(text).replace(/,/g, '').trim();
        const num = parseFloat(clean);
        if (!isNaN(num) && num > 10000 && num < 500000) {
            const canvas = this.canvas;
            const rect = canvas.getBoundingClientRect();
            const scaleY = rect.height / canvas.height;
            const screenY = Math.round(rect.top + y * scaleY);
            const isYAxisCanvas = canvas.width < 300;
            const isRightSideMain = x > canvas.width * 0.6;
            if (isYAxisCanvas || isRightSideMain) {
                window._yAxisTicks.push({ text: clean, screenY });
            }
        }
        return origFillText.call(this, text, x, y, ...args);
    };
})();
"""


# ── Browser factory ────────────────────────────────────────────────────────────

async def make_browser(pw, headless: bool):
    args = [
        "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
        "--disable-gpu", "--disable-extensions", "--hide-scrollbars", "--mute-audio",
        f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}",
    ]
    browser = await pw.chromium.launch(headless=headless, args=args)
    ctx_kwargs = dict(
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="UTC",
    )
    if SESSION_FILE.exists():
        ctx_kwargs["storage_state"] = str(SESSION_FILE)
        log.info(f"Loaded saved session from {SESSION_FILE}")
    context = await browser.new_context(**ctx_kwargs)
    await context.add_init_script(CANVAS_INTERCEPT_JS)
    page = await context.new_page()
    return browser, context, page


# ── Login ──────────────────────────────────────────────────────────────────────

async def login(page: Page) -> bool:
    if not CG_EMAIL or not CG_PASSWORD:
        log.error("COINGLASS_EMAIL / COINGLASS_PASSWORD not set in .env")
        return False

    log.info(f"Logging in as {CG_EMAIL}...")
    try:
        if SESSION_FILE.exists():
            await page.goto(CHART_URL, wait_until="networkidle", timeout=60_000)
            await page.wait_for_timeout(2000)
            if "login" not in page.url:
                log.info("Session still valid — skipping login.")
                return True
            log.info("Saved session expired — logging in fresh.")
            SESSION_FILE.unlink(missing_ok=True)

        await page.goto("https://www.coinglass.com/user/login", wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(2000)

        has_form = await page.evaluate("() => !!document.querySelector('input[type=\"email\"], input[name=\"email\"]')")
        if not has_form:
            await page.goto("https://www.coinglass.com/", wait_until="networkidle", timeout=60_000)
            await page.wait_for_timeout(1500)
            await page.click('a:has-text("Login"), button:has-text("Login")', timeout=10_000)
            await page.wait_for_timeout(2000)

        await page.locator('input[type="email"], input[name="email"]').first.fill(CG_EMAIL)
        pwd_loc = page.locator('input[type="password"], input[name="password"]').first
        await pwd_loc.fill(CG_PASSWORD)
        await pwd_loc.press("Enter")

        for _ in range(40):
            await page.wait_for_timeout(1000)
            if "login" not in page.url:
                break
        else:
            raise RuntimeError("Did not redirect away from login page in 40s")

        log.info(f"Login successful ({page.url[:60]})")
        await page.context.storage_state(path=str(SESSION_FILE))
        log.info(f"Session saved → {SESSION_FILE}")
        return True

    except Exception as e:
        log.error(f"Login failed: {e}")
        SCREENSHOT_DIR.mkdir(exist_ok=True)
        await page.screenshot(path=str(SCREENSHOT_DIR / "login_failure.png"))
        return False


# ── Chart loading ──────────────────────────────────────────────────────────────

async def _zoom_y_axis_out(page: Page) -> None:
    center_y = (CHART_Y_START + CHART_Y_END) // 2
    drag_to_y = center_y + YAXIS_DRAG_PX
    await page.mouse.move(Y_AXIS_X, center_y)
    await page.wait_for_timeout(300)
    await page.mouse.down()
    await page.mouse.move(Y_AXIS_X, drag_to_y, steps=30)
    await page.wait_for_timeout(200)
    await page.mouse.up()
    await page.wait_for_timeout(800)
    log.info(f"Y-axis dragged {YAXIS_DRAG_PX}px down (zoom out)")


async def load_chart(page: Page) -> None:
    log.info(f"Loading chart: {CHART_URL}")
    await page.goto(CHART_URL, wait_until="networkidle", timeout=60_000)
    log.info(f"Waiting {CHART_LOAD_MS}ms for chart render...")
    await page.wait_for_timeout(CHART_LOAD_MS)
    if "login" in page.url:
        raise RuntimeError("Session expired — re-login required")
    log.info("Chart ready.")
    await _zoom_y_axis_out(page)


# ── Screenshot ─────────────────────────────────────────────────────────────────

def _prune_screenshots(keep: int = 4) -> None:
    shots = sorted(SCREENSHOT_DIR.glob("scan_*.png"), key=lambda p: p.stat().st_mtime)
    for old in shots[:-keep]:
        old.unlink(missing_ok=True)


async def take_screenshot(page: Page) -> Image.Image:
    png_bytes = await page.screenshot(full_page=False)
    return Image.open(io.BytesIO(png_bytes)).convert("RGB")


# ── Line detection (pure Python — unchanged) ───────────────────────────────────

def _rightmost_colored_x(pixels, y_mid: int, label: str, width: int) -> int:
    for x in range(min(CHART_X_END, width - 1), 39, -1):
        r, g, b = pixels[x, y_mid]
        if classify_pixel(r, g, b) == label:
            return max(40, x - 5)
    return HOVER_X


def detect_lines(img: Image.Image) -> list[dict]:
    pixels = img.load()
    width, height = img.size

    # Scan multiple x columns (right → left) so lines that don't reach
    # HOVER_X are still detected. Take the rightmost hit per row.
    _scan_cols = [min(sx, width - 1) for sx in range(HOVER_X, HOVER_X - 151, -5)]
    y_labels: dict[int, str] = {}
    for sx in _scan_cols:
        for y in range(CHART_Y_START, min(CHART_Y_END, height)):
            if y in y_labels:
                continue
            r, g, b = pixels[sx, y]
            label = classify_pixel(r, g, b)
            if label:
                y_labels[y] = label

    raw: list[tuple[int, str]] = sorted(y_labels.items())

    if not raw:
        return []

    bands: list[dict] = []
    start_y, cur_label = raw[0]
    prev_y = start_y
    for y, label in raw[1:]:
        if label == cur_label and y == prev_y + 1:
            prev_y = y
        else:
            mid_y = (start_y + prev_y) // 2
            bands.append({"label": cur_label, "y": mid_y, "y_start": start_y, "y_end": prev_y})
            start_y, cur_label, prev_y = y, label, y
    mid_y = (start_y + prev_y) // 2
    bands.append({"label": cur_label, "y": mid_y, "y_start": start_y, "y_end": prev_y})

    merged: list[dict] = []
    for band in bands:
        if (merged
                and merged[-1]["label"] == band["label"]
                and band["y_start"] - merged[-1]["y_end"] <= LINE_MERGE_PX):
            merged[-1]["y_end"] = band["y_end"]
            merged[-1]["y"] = (merged[-1]["y_start"] + merged[-1]["y_end"]) // 2
        else:
            merged.append(band)

    for band in merged:
        band["hover_x"] = _rightmost_colored_x(pixels, band["y"], band["label"], width)

    log.info(f"Detected {len(merged)} colored bands")
    for b in merged:
        log.info(f"  {b['label']:<8} y={b['y']:>4}  hover_x={b['hover_x']}  (rows {b['y_start']}–{b['y_end']})")
    return merged


# ── Extraction ─────────────────────────────────────────────────────────────────

async def extract_leverage(page: Page) -> str:
    try:
        result = await page.evaluate("""() => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
            let node;
            while ((node = walker.nextNode())) {
                if (node.children.length === 0 && node.innerText?.trim() === 'Leverage') {
                    const kids = [...(node.parentElement?.children || [])];
                    const val = kids[kids.indexOf(node) + 1]?.innerText?.trim();
                    if (val) return val;
                }
            }
            return '';
        }""")
        return result or "N/A"
    except Exception as e:
        log.warning(f"leverage extract error: {e}")
        return "N/A"


def price_from_y(y: int, y_map: list[tuple[int, float]]) -> str:
    if not y_map or len(y_map) < 2:
        return "N/A"
    y_map_sorted = sorted(y_map, key=lambda t: t[0])
    if y <= y_map_sorted[0][0]:
        y1, p1 = y_map_sorted[0]; y2, p2 = y_map_sorted[1]
    elif y >= y_map_sorted[-1][0]:
        y1, p1 = y_map_sorted[-2]; y2, p2 = y_map_sorted[-1]
    else:
        for i in range(len(y_map_sorted) - 1):
            if y_map_sorted[i][0] <= y <= y_map_sorted[i + 1][0]:
                y1, p1 = y_map_sorted[i]; y2, p2 = y_map_sorted[i + 1]; break
        else:
            y1, p1 = y_map_sorted[0]; y2, p2 = y_map_sorted[-1]
    if y2 == y1:
        return f"{p1:.1f}"
    return f"{p1 + (p2 - p1) * (y - y1) / (y2 - y1):.1f}"


async def capture_y_axis_map(page: Page) -> list[tuple[int, float]]:
    try:
        ticks = await page.evaluate("() => window._yAxisTicks || []")
        raw: dict[int, list[float]] = {}
        for t in ticks:
            price = float(str(t["text"]).replace(",", ""))
            if 1000 < price < 10_000_000:
                sy = int(t["screenY"])
                bucket = round(sy / 5) * 5
                raw.setdefault(bucket, []).append(price)
        return [(bucket, sum(prices) / len(prices)) for bucket, prices in sorted(raw.items())]
    except Exception as e:
        log.warning(f"y-axis map error: {e}")
        return []


# ── Collection ─────────────────────────────────────────────────────────────────

CSV_FIELDS = ["timestamp", "color", "y_pixel", "y_range", "leverage", "price"]


def ensure_csv_header() -> None:
    if not os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()
        log.info(f"Created {OUTPUT_CSV}")


def append_csv(rows: list[dict]) -> None:
    with open(OUTPUT_CSV, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writerows(rows)
    log.info(f"Appended {len(rows)} rows → {OUTPUT_CSV}")


async def collect_all_lines(page: Page, timestamp: str) -> list[dict]:
    img = await take_screenshot(page)
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    snap = SCREENSHOT_DIR / f"scan_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.png"
    img.save(str(snap))
    _prune_screenshots(keep=4)

    lines = detect_lines(img)
    img.close()
    if not lines:
        log.warning("No colored lines detected")
        return []

    y_map = await capture_y_axis_map(page)
    log.info(f"Y-axis map: {len(y_map)} ticks captured")

    # Fixed x = last candle (just left of Y-axis). Only move vertically per line.
    _fixed_x = CHART_X_END - 5
    await page.mouse.move(_fixed_x, 400)
    await page.wait_for_timeout(200)

    rows = []
    for i, line in enumerate(lines):
        try:
            await page.mouse.move(_fixed_x, line["y"])
            await page.wait_for_timeout(HOVER_SETTLE_MS)
            leverage = await extract_leverage(page)
            if leverage in ("N/A", "ERROR", ""):
                log.info(f"  [{i+1:02d}] {line['label']:<8} y={line['y']:>4} | skipped (no tooltip)")
                continue
            price = price_from_y(line["y"], y_map)
            row = {
                "timestamp": timestamp,
                "color":     line["label"],
                "y_pixel":   line["y"],
                "y_range":   f"{line['y_start']}-{line['y_end']}",
                "leverage":  leverage,
                "price":     price,
            }
            rows.append(row)
            log.info(f"  [{i+1:02d}] {line['label']:<8} y={line['y']:>4} | Leverage: {leverage:<12} | Price: {price}")
        except Exception as e:
            log.error(f"Error on line {line['label']} y={line['y']}: {e}")
            rows.append({
                "timestamp": timestamp, "color": line["label"],
                "y_pixel": line["y"], "y_range": f"{line['y_start']}-{line['y_end']}",
                "leverage": "ERROR", "price": str(e)[:80],
            })
    return rows


# ── Main loops ─────────────────────────────────────────────────────────────────

async def run_collect() -> None:
    """Full collection loop — kill-and-restart playwright every 15 min."""
    if not log.handlers:
        _configure_logging()
    ensure_csv_header()
    log.info("CoinGlass Leverage Collector starting (Playwright kill-restart mode)...")
    run_count = 0
    while True:
        run_count += 1
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        log.info(f"\n{'='*60}\nRun #{run_count} — {timestamp}\n{'='*60}")
        try:
            async with async_playwright() as pw:
                browser, context, page = await make_browser(pw, headless=True)
                try:
                    if not await login(page):
                        log.error("Login failed — skipping run.")
                    else:
                        await load_chart(page)
                        rows = await collect_all_lines(page, timestamp)
                        if rows:
                            append_csv(rows)
                except Exception as e:
                    log.exception(f"Run #{run_count} inner error: {e}")
                finally:
                    await context.close()
                    await browser.close()
        except Exception as e:
            log.exception(f"Run #{run_count} playwright error: {e}")
        log.info(f"Sleeping {INTERVAL_SECONDS // 60}m...")
        await asyncio.sleep(INTERVAL_SECONDS)


async def run_debug() -> None:
    """One-shot headed browser — inspect chart manually."""
    log.info("DEBUG MODE — headed browser, one-shot DOM dump")
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser, context, page = await make_browser(pw, headless=False)
        try:
            if not await login(page):
                log.error("Cannot proceed without login.")
                return
            await load_chart(page)

            img = await take_screenshot(page)
            debug_shot = SCREENSHOT_DIR / "debug_before_hover.png"
            img.save(str(debug_shot))
            log.info(f"Screenshot saved → {debug_shot}")

            y_map = await capture_y_axis_map(page)
            log.info(f"Y-axis ticks captured: {len(y_map)}")
            for sy, pr in sorted(y_map)[:10]:
                log.info(f"  screen_y={sy:>4}  price={pr:,.1f}")

            lines = detect_lines(img)
            if not lines:
                log.warning("No colored lines — check color profiles or HOVER_X")
            else:
                _fixed_x = CHART_X_END - 5
                await page.mouse.move(_fixed_x, 400)
                await page.wait_for_timeout(200)
                for line in lines:
                    await page.mouse.move(_fixed_x, line["y"])
                    await page.wait_for_timeout(HOVER_SETTLE_MS)
                    lev   = await extract_leverage(page)
                    price = price_from_y(line["y"], y_map)
                    log.info(f"  {line['label']:<8} y={line['y']:>4} | Leverage: {lev:<12} | Price: {price}")

            log.info("Keeping browser open for 30s — inspect manually if needed.")
            await asyncio.sleep(30)
        finally:
            await context.close()
            await browser.close()


# ── Entry points ───────────────────────────────────────────────────────────────

def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            RotatingFileHandler("collector.log", maxBytes=5 * 1024 * 1024, backupCount=3),
            logging.StreamHandler(),
        ],
    )


def debug_main() -> None:
    _configure_logging()
    asyncio.run(run_debug())


def collect_main() -> None:
    _configure_logging()
    asyncio.run(run_collect())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    debug_main() if args.debug else collect_main()
