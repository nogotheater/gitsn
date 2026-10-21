"""Verify the installed Playwright browser, without building the product PDF feature."""
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright

with sync_playwright() as manager:
    browser = manager.chromium.launch()
    if browser.version != "156.0.8078.4":
        browser.close()
        raise SystemExit("Browser version does not match the recorded Playwright version.")
    page = browser.new_page()
    page.set_content("<!doctype html><html><body><h1>GITSN stage 1</h1></body></html>")
    assert page.title() == ""
    assert page.locator("h1").inner_text() == "GITSN stage 1"
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "probe.pdf"
        page.pdf(path=str(target))
        assert target.read_bytes().startswith(b"%PDF")
    print("Playwright Chromium verified:", browser.version)
    browser.close()
