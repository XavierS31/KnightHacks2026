"""Fixed UI regression: the product page in this tree loads its sample and enables execution.

Run from the tree under test. It starts that tree's product on a free loopback port, drives
Chromium, and exits nonzero on failure. It needs no Docker image, HF access or database.
"""
import asyncio
import socket
import subprocess
import sys

import httpx
from playwright.async_api import async_playwright


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


async def check(base_url: str) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(base_url, wait_until="networkidle")
            await page.get_by_role("heading", name="Choose a document").wait_for()
            await page.locator("#load-sample").click()
            await page.get_by_text("Sample inventory.pdf", exact=True).wait_for(timeout=10_000)
            await page.locator("#execute:not([disabled])").wait_for(timeout=10_000)
            names = await page.locator("#columns input:not([type=checkbox])").evaluate_all(
                "inputs => inputs.map(input => input.value)")
            if names != ["Item", "Quantity", "Unit price"]:
                raise AssertionError(f"Sample columns did not render: {names}")
            await page.set_viewport_size({"width": 390, "height": 844})
            overflow = await page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth")
            if overflow:
                raise AssertionError("The product page scrolls horizontally at 390px.")
            if errors:
                raise AssertionError(f"Page errors: {errors}")
        finally:
            await browser.close()


async def run() -> None:
    port = free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.features.integration.product.app:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"])
    base_url = f"http://127.0.0.1:{port}/"
    try:
        async with httpx.AsyncClient() as client:
            for _ in range(60):
                if server.poll() is not None:
                    raise AssertionError("The product process exited before it served the page.")
                try:
                    if (await client.get(base_url)).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.25)
            else:
                raise AssertionError("The product page did not start within 15 seconds.")
        await check(base_url)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    asyncio.run(run())
    print("Product UI check passed.")
