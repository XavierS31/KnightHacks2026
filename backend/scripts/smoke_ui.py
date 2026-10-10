"""Optional actual browser QA of the local fixture dashboard; not a persona experiment."""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


async def run():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto("http://127.0.0.1:5173", wait_until="networkidle")
        await page.get_by_role("heading", name="Integration", exact=True).wait_for()
        await page.get_by_text("Candidate evidence", exact=True).wait_for()
        await page.get_by_role("button", name="Load fixture candidates", exact=True).click()
        await page.get_by_text("fixture · fixture", exact=True).wait_for()
        await page.get_by_role("button", name="02 Personas").click()
        await page.get_by_role("heading", name="Personas", exact=True).wait_for()
        await page.get_by_text("Required per version", exact=True).wait_for()
        await page.get_by_text("fixture stream connected", exact=False).wait_for()
        await page.get_by_role("button", name="Synthetic persona 02").click()
        await page.get_by_role("heading", name="Synthetic persona 02", exact=True).wait_for()
        await page.get_by_text("fixture stream connected", exact=False).wait_for()
        await page.get_by_role("heading", name="Software behavior · fixture", exact=True).wait_for()
        await page.get_by_text("Try a sample before uploading personal documents", exact=True).wait_for()
        await page.get_by_text("Illustrative fixture", exact=False).wait_for()
        await page.screenshot(path="artifacts/scaffold-personas.png", full_page=True)
        await page.set_viewport_size({"width": 390, "height": 844})
        if await page.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
            raise RuntimeError("Persona behavior view overflows on mobile")
        await page.screenshot(path="artifacts/scaffold-personas-mobile.png", full_page=True)
        await page.set_viewport_size({"width": 1440, "height": 1000})
        await page.get_by_role("button", name="03 Evolution").click()
        await page.get_by_role("heading", name="Evolution", exact=True).wait_for()
        await page.get_by_text("Analyst", exact=False).wait_for()
        await page.get_by_role("button", name="Analyze stored fixture sessions", exact=True).click()
        await page.get_by_text("No supported improvements were created.", exact=False).wait_for()
        artifact = Path("artifacts/scaffold-desktop.png")
        artifact.parent.mkdir(exist_ok=True)
        await page.screenshot(path=str(artifact), full_page=True)
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.get_by_role("button", name="01 Integration").click()
        await page.get_by_role("heading", name="Integration", exact=True).wait_for()
        overflow = await page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        if overflow:
            raise RuntimeError("Mobile layout overflows horizontally")
        await page.screenshot(path="artifacts/scaffold-mobile.png", full_page=True)
        await browser.close()
        if errors:
            raise RuntimeError(f"Browser errors: {errors}")
    print("Desktop/mobile fixture navigation passed; screenshots under artifacts/. Not persona results.")


if __name__ == "__main__":
    asyncio.run(run())
