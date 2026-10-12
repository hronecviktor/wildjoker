"""Render icon.svg to the PNG sizes the web app manifest and iOS need.

Run from frontend/ in the Playwright image (any image with playwright works):

    docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v ~/envs/wildjoker-e2e:/deps \
      -e PYTHONPATH=/deps -v "$PWD:/f" mcr.microsoft.com/playwright/python:v1.58.0-noble \
      sh -c 'python3 /f/icon-src/render.py /f/public/icons && cp /f/icon-src/icon.svg /f/public/icons/'
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

here = Path(__file__).parent
out = Path(sys.argv[1]) if len(sys.argv) > 1 else here.parent / "public" / "icons"
svg = (here / "icon.svg").read_text()
# name: (size, corner radius as a share of the size; 0 = full bleed)
SIZES = {
    "icon-192.png": (192, 0.22),
    "icon-512.png": (512, 0.22),
    "maskable-512.png": (512, 0),  # Android crops it to its own shape
    "apple-touch-icon.png": (180, 0),  # iOS rounds the corners itself
    "favicon-32.png": (32, 0.18),
}
with sync_playwright() as p:
    browser = p.chromium.launch()
    for name, (size, radius) in SIZES.items():
        page = browser.new_page(viewport={"width": size, "height": size})
        page.set_content(
            f"<style>html,body{{margin:0;background:transparent}}"
            f"svg{{display:block;width:{size}px;height:{size}px;border-radius:{radius * size}px}}</style>{svg}"
        )
        page.screenshot(path=str(out / name), omit_background=True)
        page.close()
    browser.close()
print("wrote", ", ".join(SIZES), "to", out)
