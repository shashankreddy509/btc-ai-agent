"""
CoinGlass Liquidation Heatmap — Dynamic Leverage Collector (Selenium)

Kill-and-restart pattern: browser opens, scrapes, quits every 15 min.
Memory: ~400 MB for ~30s per cycle, then 0 during sleep.

Usage:
    uv run liquidity-debug     # one-shot hover + DOM dump, headed browser
    uv run liquidity-collect   # full 15-min loop, headless
"""

import csv
import io
import json
import logging
import os
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

load_dotenv()

log = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
CHART_URL        = "https://legend.coinglass.com/chart/93ab9a7dbf63446c9c2b9944f10e6ef2"
SESSION_FILE     = Path(".coinglass_cookies.json")
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

def _make_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-setuid-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--hide-scrollbars")
    opts.add_argument("--mute-audio")
    opts.add_argument(f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=opts)
    driver.set_window_size(VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
    # Inject canvas intercept — fires before every subsequent driver.get()
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument", {"source": CANVAS_INTERCEPT_JS}
    )
    return driver


# ── Session persistence ────────────────────────────────────────────────────────

def _save_session(driver: webdriver.Chrome) -> None:
    cookies = driver.get_cookies()
    SESSION_FILE.write_text(json.dumps(cookies))
    log.info(f"Session saved → {SESSION_FILE} ({len(cookies)} cookies)")


def _load_session(driver: webdriver.Chrome) -> bool:
    if not SESSION_FILE.exists():
        return False
    try:
        # Must navigate to the domain before adding cookies
        driver.get("https://www.coinglass.com")
        time.sleep(1)
        for cookie in json.loads(SESSION_FILE.read_text()):
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass
        log.info(f"Session loaded from {SESSION_FILE}")
        return True
    except Exception as e:
        log.warning(f"Session load failed: {e}")
        return False


# ── Mouse helpers (CDP — absolute viewport coordinates) ───────────────────────

def _mouse_move(driver: webdriver.Chrome, x: int, y: int) -> None:
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
        "type": "mouseMoved", "x": x, "y": y, "button": "none",
    })


def _mouse_drag(driver: webdriver.Chrome, x: int, y_start: int, y_end: int, steps: int = 30) -> None:
    _mouse_move(driver, x, y_start)
    time.sleep(0.3)
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": x, "y": y_start, "button": "left", "clickCount": 1,
    })
    for step in range(steps):
        y = y_start + int((y_end - y_start) * (step + 1) / steps)
        _mouse_move(driver, x, y)
        time.sleep(0.01)
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": x, "y": y_end, "button": "left", "clickCount": 1,
    })
    time.sleep(0.8)


# ── Login ──────────────────────────────────────────────────────────────────────

def login(driver: webdriver.Chrome) -> bool:
    if not CG_EMAIL or not CG_PASSWORD:
        log.error("COINGLASS_EMAIL / COINGLASS_PASSWORD not set in .env")
        return False

    log.info(f"Logging in as {CG_EMAIL}...")
    try:
        # Try existing session first
        if SESSION_FILE.exists():
            _load_session(driver)
            driver.get(CHART_URL)
            time.sleep(2)
            if "login" not in driver.current_url:
                log.info("Session still valid — skipping login.")
                return True
            log.info("Saved session expired — logging in fresh.")
            SESSION_FILE.unlink(missing_ok=True)

        driver.get("https://www.coinglass.com/user/login")
        time.sleep(2)

        has_form = driver.execute_script(
            "return !!document.querySelector('input[type=\"email\"], input[name=\"email\"]')"
        )
        if not has_form:
            driver.get("https://www.coinglass.com/")
            time.sleep(1.5)
            try:
                btn = driver.find_element(By.XPATH, '//a[contains(text(),"Login")] | //button[contains(text(),"Login")]')
                btn.click()
                time.sleep(2)
            except Exception:
                pass

        email_input = driver.find_element(By.CSS_SELECTOR, 'input[type="email"], input[name="email"]')
        email_input.send_keys(CG_EMAIL)

        pwd_input = driver.find_element(By.CSS_SELECTOR, 'input[type="password"], input[name="password"]')
        pwd_input.send_keys(CG_PASSWORD)
        pwd_input.send_keys(Keys.RETURN)

        # Wait up to 40s for redirect away from login
        for _ in range(40):
            time.sleep(1)
            if "login" not in driver.current_url:
                break
        else:
            raise RuntimeError("Did not redirect away from login page in 40s")

        log.info(f"Login successful ({driver.current_url[:60]})")
        _save_session(driver)
        return True

    except Exception as e:
        log.error(f"Login failed: {e}")
        SCREENSHOT_DIR.mkdir(exist_ok=True)
        driver.save_screenshot(str(SCREENSHOT_DIR / "login_failure.png"))
        return False


# ── Chart loading ──────────────────────────────────────────────────────────────

def _zoom_y_axis_out(driver: webdriver.Chrome) -> None:
    center_y = (CHART_Y_START + CHART_Y_END) // 2
    _mouse_drag(driver, Y_AXIS_X, center_y, center_y + YAXIS_DRAG_PX)
    log.info(f"Y-axis dragged {YAXIS_DRAG_PX}px down (zoom out)")


def load_chart(driver: webdriver.Chrome) -> None:
    log.info(f"Loading chart: {CHART_URL}")
    driver.get(CHART_URL)
    log.info(f"Waiting {CHART_LOAD_MS}ms for chart render...")
    time.sleep(CHART_LOAD_MS / 1000)
    if "login" in driver.current_url:
        raise RuntimeError("Session expired — re-login required")
    log.info("Chart ready.")
    _zoom_y_axis_out(driver)


# ── Screenshot ─────────────────────────────────────────────────────────────────

def _prune_screenshots(keep: int = 4) -> None:
    shots = sorted(SCREENSHOT_DIR.glob("scan_*.png"), key=lambda p: p.stat().st_mtime)
    for old in shots[:-keep]:
        old.unlink(missing_ok=True)


def take_screenshot(driver: webdriver.Chrome) -> Image.Image:
    png_bytes = driver.get_screenshot_as_png()
    return Image.open(io.BytesIO(png_bytes)).convert("RGB")


# ── Line detection (pure Python — unchanged from playwright version) ───────────

def _rightmost_colored_x(pixels, y_mid: int, label: str, width: int) -> int:
    for x in range(min(CHART_X_END, width - 1), 39, -1):
        r, g, b = pixels[x, y_mid]
        if classify_pixel(r, g, b) == label:
            return max(40, x - 5)
    return HOVER_X


def detect_lines(img: Image.Image) -> list[dict]:
    pixels = img.load()
    width, height = img.size
    x = min(HOVER_X, width - 1)

    raw: list[tuple[int, str]] = []
    for y in range(CHART_Y_START, min(CHART_Y_END, height)):
        r, g, b = pixels[x, y]
        label = classify_pixel(r, g, b)
        if label:
            raw.append((y, label))

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

def extract_leverage(driver: webdriver.Chrome) -> str:
    try:
        result = driver.execute_script("""
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
        """)
        return result or "N/A"
    except Exception as e:
        log.warning(f"leverage extract error: {e}")
        return "N/A"


def price_from_y(y: int, y_map: list[tuple[int, float]]) -> str:
    if not y_map or len(y_map) < 2:
        return "N/A"
    y_map_sorted = sorted(y_map, key=lambda t: t[0])
    if y <= y_map_sorted[0][0]:
        y1, p1 = y_map_sorted[0]
        y2, p2 = y_map_sorted[1]
    elif y >= y_map_sorted[-1][0]:
        y1, p1 = y_map_sorted[-2]
        y2, p2 = y_map_sorted[-1]
    else:
        for i in range(len(y_map_sorted) - 1):
            if y_map_sorted[i][0] <= y <= y_map_sorted[i + 1][0]:
                y1, p1 = y_map_sorted[i]
                y2, p2 = y_map_sorted[i + 1]
                break
        else:
            y1, p1 = y_map_sorted[0]
            y2, p2 = y_map_sorted[-1]
    if y2 == y1:
        return f"{p1:.1f}"
    price = p1 + (p2 - p1) * (y - y1) / (y2 - y1)
    return f"{price:.1f}"


def capture_y_axis_map(driver: webdriver.Chrome) -> list[tuple[int, float]]:
    try:
        ticks = driver.execute_script("return window._yAxisTicks || []")
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


def collect_all_lines(driver: webdriver.Chrome, timestamp: str) -> list[dict]:
    img = take_screenshot(driver)
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    snap = SCREENSHOT_DIR / f"scan_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.png"
    img.save(str(snap))
    _prune_screenshots(keep=4)

    lines = detect_lines(img)
    img.close()
    if not lines:
        log.warning("No colored lines detected")
        return []

    y_map = capture_y_axis_map(driver)
    log.info(f"Y-axis map: {len(y_map)} ticks captured")

    _mouse_move(driver, lines[0]["hover_x"], 400)
    time.sleep(0.2)

    rows = []
    for i, line in enumerate(lines):
        try:
            _mouse_move(driver, line["hover_x"], line["y"])
            time.sleep(HOVER_SETTLE_MS / 1000)
            leverage = extract_leverage(driver)
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
                "timestamp": timestamp,
                "color":     line["label"],
                "y_pixel":   line["y"],
                "y_range":   f"{line['y_start']}-{line['y_end']}",
                "leverage":  "ERROR",
                "price":     str(e)[:80],
            })
    return rows


# ── Main loops ─────────────────────────────────────────────────────────────────

def run_collect() -> None:
    """Full collection loop — kill-and-restart every 15 min."""
    ensure_csv_header()
    log.info("CoinGlass Leverage Collector starting (Selenium kill-restart mode)...")
    run_count = 0
    while True:
        run_count += 1
        driver = None
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            log.info(f"\n{'='*60}\nRun #{run_count} — {timestamp}\n{'='*60}")
            driver = _make_driver(headless=True)
            if not login(driver):
                log.error("Login failed — skipping run.")
            else:
                load_chart(driver)
                rows = collect_all_lines(driver, timestamp)
                if rows:
                    append_csv(rows)
        except Exception as e:
            log.exception(f"Run #{run_count} failed: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
        log.info(f"Sleeping {INTERVAL_SECONDS // 60}m...")
        time.sleep(INTERVAL_SECONDS)


def run_debug() -> None:
    """One-shot headed browser — inspect chart manually."""
    log.info("DEBUG MODE — headed browser, one-shot DOM dump")
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    driver = _make_driver(headless=False)
    try:
        if not login(driver):
            log.error("Cannot proceed without login.")
            return

        load_chart(driver)

        img = take_screenshot(driver)
        debug_shot = SCREENSHOT_DIR / "debug_before_hover.png"
        img.save(str(debug_shot))
        log.info(f"Screenshot saved → {debug_shot}")

        y_map = capture_y_axis_map(driver)
        log.info(f"Y-axis ticks captured: {len(y_map)}")
        for sy, pr in sorted(y_map)[:10]:
            log.info(f"  screen_y={sy:>4}  price={pr:,.1f}")

        lines = detect_lines(img)
        if not lines:
            log.warning("No colored lines — check color profiles or HOVER_X")
        else:
            _mouse_move(driver, lines[0]["hover_x"], 400)
            time.sleep(0.2)
            for line in lines:
                _mouse_move(driver, line["hover_x"], line["y"])
                time.sleep(HOVER_SETTLE_MS / 1000)
                lev   = extract_leverage(driver)
                price = price_from_y(line["y"], y_map)
                log.info(f"  {line['label']:<8} y={line['y']:>4} | Leverage: {lev:<12} | Price: {price}")

        log.info("Keeping browser open for 30s — inspect manually if needed.")
        time.sleep(30)
    finally:
        driver.quit()


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
    run_debug()


def collect_main() -> None:
    _configure_logging()
    run_collect()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    debug_main() if args.debug else collect_main()
