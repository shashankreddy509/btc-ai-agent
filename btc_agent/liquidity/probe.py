"""One-shot probe: find chart API + correct selectors for leverage and price."""
import asyncio
import io
from dotenv import load_dotenv
from PIL import Image
from playwright.async_api import async_playwright
from btc_agent.liquidity.collector import make_browser, login, load_chart, CHART_URL

load_dotenv()


async def main():
    async with async_playwright() as pw:
        browser, context, page = await make_browser(pw, headless=False)

        print("Logging in...")
        if not await login(page):
            print("Login failed.")
            return
        print("Loading chart...")
        await load_chart(page)

        import pathlib
        pathlib.Path("screenshots").mkdir(exist_ok=True)
        png = await page.screenshot(full_page=False)
        img = Image.open(io.BytesIO(png)).convert("RGB")
        img.save("screenshots/probe_shot.png")

        pixels = img.load()
        width, height = img.size
        results_by_x = {}
        for test_x in [1250, 1220, 1200, 1180, 1150, 1100, 800, 600]:
            found = []
            for y in range(55, 740):
                r, g, b = pixels[min(test_x, width - 1), y]
                if (220 <= r <= 255 and 220 <= g <= 255 and 0 <= b <= 40):
                    found.append(("YELLOW", y))
                elif (220 <= r <= 255 and 80 <= g <= 180 and 0 <= b <= 40):
                    found.append(("ORANGE", y))
                elif (0 <= r <= 25 and 0 <= g <= 25 and 0 <= b <= 25):
                    found.append(("BLACK", y))
            if found:
                results_by_x[test_x] = found[:3]
        print("Colored pixels by X:", results_by_x)

        best_x, best_y = 1250, 367
        for tx in [1250, 1220, 1200, 1180, 1150, 1100, 800, 600]:
            if tx in results_by_x:
                best_x = tx
                best_y = results_by_x[tx][0][1]
                break
        print(f"Hovering at x={best_x}, y={best_y}")

        await page.mouse.move(best_x, 400)
        await page.wait_for_timeout(300)
        await page.mouse.move(best_x, best_y)
        await page.wait_for_timeout(1200)

        result = await page.evaluate("""() => {
            const found = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
            let node;
            while ((node = walker.nextNode())) {
                if (node.children.length === 0 && node.innerText?.trim() === 'Leverage') {
                    const parent = node.parentElement;
                    const grandparent = parent?.parentElement;
                    const kids = [...(parent?.children || [])];
                    const idx = kids.indexOf(node);
                    found.push({
                        parentClass: parent?.className?.substring(0, 60),
                        grandparentClass: grandparent?.className?.substring(0, 60),
                        numKids: kids.length,
                        idx: idx,
                        nextText: kids[idx+1]?.innerText?.trim(),
                        parentInnerText: parent?.innerText?.replace(/\\n/g,' ').trim().substring(0, 80),
                    });
                }
            }
            const allText = document.body.innerText;
            const priceMatches = allText.match(/\\b8[0-9],[0-9]{3}(?:\\.[0-9]+)?\\b/g) || [];
            return { found, priceMatches: [...new Set(priceMatches)] };
        }""")

        print("Leverage elements found:")
        for f in result["found"]:
            print(" ", f)
        print("Price matches:", result["priceMatches"])

        await context.close()
        await browser.close()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
